'''Learns readable names for scrambled BinOutput keys by matching values against a readable source.

Some builds replace every JSON key (and every "$type" class name) with an 11-letter token, consistently
across all files of that build. The same files from a readable source contain the same values, so
walking both copies in parallel and pairing fields whose values match recovers the names.
'''
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import re


SCRAMBLED = re.compile(r'[A-Z]{11}')
TYPE = '$type'


def is_scrambled(key):
    return isinstance(key, str) and SCRAMBLED.fullmatch(key) is not None


def normalize(value):
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        # Sources differ in float precision (0.1 vs 0.10000000149011612) and int/float spelling.
        return f'{float(value):.6g}'
    return value


class Leaves:
    '''Multiset of primitive values under a node ($type names excluded, since they are scrambled too).'''

    def __init__(self):
        self.cache = {}

    def __call__(self, value):
        key = id(value)
        if key not in self.cache:
            counter = Counter()
            if isinstance(value, dict):
                for name, child in value.items():
                    if name != TYPE:
                        counter.update(self(child))
            elif isinstance(value, list):
                for child in value:
                    counter.update(self(child))
            else:
                counter[normalize(value)] += 1
            self.cache[key] = counter
        return self.cache[key]


def kind(value):
    return 'dict' if isinstance(value, dict) else 'list' if isinstance(value, list) else 'value'


def similarity(leaves, a, b):
    '''(share of the readable values found in the scrambled copy, overlap ratio) for tie-breaking.

    Scrambled sources may also write out default values the readable source omits, so containment
    is the primary score rather than a symmetric overlap.
    '''
    if kind(a) != kind(b):
        return 0.0, 0.0
    if kind(a) == 'value':
        return (1.0, 1.0) if normalize(a) == normalize(b) else (0.0, 0.0)
    left, right = leaves(a), leaves(b)
    size = sum(left.values())
    if not size:
        return 0.0, 0.0
    shared = sum((left & right).values())
    return shared / size, shared / sum((left | right).values())


class Learner:
    def __init__(self, known=None, known_types=None):
        self.keys = defaultdict(Counter)
        self.types = defaultdict(Counter)
        self.known = known or {}
        self.known_types = known_types or {}

    def align(self, readable, scrambled, leaves):
        if isinstance(readable, dict) and isinstance(scrambled, dict):
            if isinstance(readable.get(TYPE), str) and isinstance(scrambled.get(TYPE), str):
                self.types[scrambled[TYPE]][readable[TYPE]] += 1
            for name_a, name_b in self.pair_keys(readable, scrambled, leaves):
                if is_scrambled(name_b) and name_a != name_b:
                    self.keys[name_b][name_a] += 1
                self.align(readable[name_a], scrambled[name_b], leaves)
        elif isinstance(readable, list) and isinstance(scrambled, list):
            if len(readable) == len(scrambled):
                for a, b in zip(readable, scrambled):
                    self.align(a, b, leaves)
            else:
                for a, b in self.greedy(list(enumerate(readable)), list(enumerate(scrambled)), leaves):
                    self.align(readable[a], scrambled[b], leaves)

    def pair_keys(self, readable, scrambled, leaves):
        pairs = []
        left = {name for name in readable if name != TYPE}
        right = []
        for name in scrambled:
            if name == TYPE:
                continue
            target = name if name in left else self.known.get(name)
            if target in left:
                pairs.append((target, name))
                left.discard(target)
            else:
                right.append(name)
        # Primitive values pair only when the value is unique among the remaining fields on both sides.
        by_value_a, by_value_b = defaultdict(list), defaultdict(list)
        for name in left:
            if kind(readable[name]) == 'value':
                by_value_a[normalize(readable[name])].append(name)
        for name in right:
            if kind(scrambled[name]) == 'value':
                by_value_b[normalize(scrambled[name])].append(name)
        for value, names in by_value_b.items():
            if len(names) == 1 and len(by_value_a.get(value, [])) == 1:
                pairs.append((by_value_a[value][0], names[0]))
                left.discard(by_value_a[value][0])
                right.remove(names[0])
        containers_a = [(name, readable[name]) for name in left if kind(readable[name]) != 'value']
        containers_b = [(name, scrambled[name]) for name in right if kind(scrambled[name]) != 'value']
        matched = self.greedy(containers_a, containers_b, leaves)
        pairs += matched
        # A lone leftover container on each side is the same field when its class is already known to match.
        rest_a = [item for item in containers_a if item[0] not in {a for a, _ in matched}]
        rest_b = [item for item in containers_b if item[0] not in {b for _, b in matched}]
        if len(rest_a) == 1 and len(rest_b) == 1 and self.same_class(rest_a[0][1], rest_b[0][1]):
            pairs.append((rest_a[0][0], rest_b[0][0]))
        return pairs

    def same_class(self, readable, scrambled):
        if isinstance(readable, list) and isinstance(scrambled, list):
            readable, scrambled = readable[:1], scrambled[:1]
            if not readable or not scrambled:
                return False
            readable, scrambled = readable[0], scrambled[0]
        return (isinstance(readable, dict) and isinstance(scrambled, dict)
                and readable.get(TYPE) is not None
                and self.known_types.get(scrambled.get(TYPE), scrambled.get(TYPE)) == readable.get(TYPE))

    def greedy(self, items_a, items_b, leaves, threshold=0.6):
        scores = []
        for name_a, a in items_a:
            for name_b, b in items_b:
                containment, overlap = similarity(leaves, a, b)
                scores.append(((containment, self.same_class(a, b), overlap), name_a, name_b))
        scores.sort(key=lambda item: item[0], reverse=True)
        used_a, used_b, pairs = set(), set(), []
        for (containment, _, _), name_a, name_b in scores:
            if containment < threshold:
                break
            if name_a not in used_a and name_b not in used_b:
                used_a.add(name_a)
                used_b.add(name_b)
                pairs.append((name_a, name_b))
        return pairs


def decide(votes, min_share=0.6):
    '''Majority readable name per token.

    Several tokens may share a readable name: builds scramble each class's fields separately.
    '''
    chosen = {}
    for token, counter in votes.items():
        name, count = counter.most_common(1)[0]
        if count / sum(counter.values()) >= min_share:
            chosen[token] = name
    return chosen


def shared_files(readable_root, scrambled_root):
    readable = {path.relative_to(readable_root) for path in readable_root.rglob('*.json')}
    return sorted(path for path in (p.relative_to(scrambled_root) for p in scrambled_root.rglob('*.json')) if path in readable)


def load(path):
    with path.open(encoding='utf-8') as file:
        return json.load(file)


def monster_pairs(monster_table, readable_dir, scrambled_dir):
    '''Pairs monster configs whose file names differ between sources, using the monster Excel table.'''
    with Path(monster_table).open(encoding='utf-8') as file:
        monsters = json.load(file)
    readable = {path.stem: path for path in readable_dir.glob('*.json')}
    scrambled = {path.stem: path for path in scrambled_dir.glob('*.json')}
    by_id = {}
    for stem, path in scrambled.items():
        tail = stem.rsplit('_', 1)[-1]
        if tail.isdigit():
            by_id.setdefault(int(tail), path)
    pairs = set()
    for monster in monsters:
        name, identifier = monster.get('MonsterName'), monster.get('Id')
        left = readable.get(f'ConfigMonster_{name}') or readable.get(str(name)) or readable.get(str(identifier))
        right = by_id.get(identifier) or scrambled.get(str(name))
        if left and right:
            pairs.add((left, right))
    return sorted(pairs)


def learn(readable_root, scrambled_root, extra_pairs=(), passes=3):
    '''Returns ({token: key}, {token: type name}, number of file pairs compared).

    Files with the same relative path are compared; extra_pairs adds (readable, scrambled) file pairs
    that the two sources name differently (such as hash-named monster configs).
    '''
    pairs = [(readable_root / relative, scrambled_root / relative) for relative in shared_files(readable_root, scrambled_root)]
    pairs += list(extra_pairs)
    keys, types = {}, {}
    for _ in range(passes):
        learner = Learner(keys, types)
        for readable, scrambled in pairs:
            try:
                learner.align(load(readable), load(scrambled), Leaves())
            except (OSError, ValueError):
                continue
        keys, types = decide(learner.keys), decide(learner.types)
    return keys, types, len(pairs)


def translate(value, keys, types):
    if isinstance(value, dict):
        result = {}
        taken = set()
        for name, child in value.items():
            if name == TYPE and isinstance(child, str):
                result[name] = types.get(child, child)
                continue
            target = keys.get(name, name)
            # Never let a learned name overwrite a sibling field; keep the token instead.
            if target != name and (target in value or target in taken):
                target = name
            taken.add(target)
            result[target] = translate(child, keys, types)
        return result
    if isinstance(value, list):
        return [translate(child, keys, types) for child in value]
    return value


def apply(root, keys, types):
    '''Rewrites every JSON file under root with readable names; returns (translated, remaining) key counts.'''
    translated = remaining = 0
    for path in root.rglob('*.json'):
        data = load(path)
        result = translate(data, keys, types)

        def count(value):
            if isinstance(value, dict):
                return sum(is_scrambled(name) + count(child) for name, child in value.items())
            if isinstance(value, list):
                return sum(count(child) for child in value)
            return 0

        before, after = count(data), count(result)
        translated += before - after
        remaining += after
        temporary = path.with_name(f'.{path.name}.tmp')
        with temporary.open('w', encoding='utf-8') as file:
            json.dump(result, file, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    return translated, remaining


def looks_scrambled(root, sample_size=40):
    '''True when most top-level keys of the character configs (or monster configs) are tokens.'''
    files = sorted((root / 'Avatar').glob('*.json')) or sorted((root / 'Monster').glob('*.json'))
    names = []
    for path in files[::max(1, len(files) // sample_size)]:
        try:
            data = load(path)
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            names += list(data)
    return bool(names) and sum(map(is_scrambled, names)) / len(names) > 0.5


def deobfuscate(readable_root, scrambled_root, monster_table=None):
    '''Learns names from readable_root and rewrites scrambled_root in place; returns a summary.'''
    extra = []
    if monster_table is not None and Path(monster_table).is_file():
        extra = monster_pairs(monster_table, readable_root / 'Monster', scrambled_root / 'Monster')
    keys, types, pairs = learn(readable_root, scrambled_root, extra)
    translated, remaining = apply(scrambled_root, keys, types)
    return {'keys': keys, 'types': types, 'pairs': pairs, 'translated': translated, 'remaining': remaining}
