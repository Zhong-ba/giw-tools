"""Shared Other Languages formatting and TextMap lookup, without desktop UI dependencies."""

OUTORDER = {
    'zhs': 'CHS',
    'zht': 'CHT',
    'ja': 'JP',
    'ko': 'KR',
    'es': 'ES',
    'fr': 'FR',
    'ru': 'RU',
    'th': 'TH',
    'vi': 'VI',
    'de': 'DE',
    'id': 'ID',
    'pt': 'PT',
    'tr': 'TR',
    'it': 'IT',
}
REMOVE = [
    'Normal Attack: ',
    '普通攻击·',
    '普通攻擊·',
    '通常攻撃·',
    '通常攻撃・'
    '일반 공격·',
    'Ataque Normal: ',
    'Attaque normale : ',
    'โจมตีปกติ: ',
    'Tấn Công Thường - ',
    'Standardangriff: ',
    'Ataque Normal: ',
    'Normal Saldırı: ',
    'Attacco normale: ',
    "Night Realm's Gift: ",
    '夜域赐礼·',
    '夜域賜禮·',
    '夜域の賜物·',
    '밤 영역의 선물·',
    'Gracia de la noche: ',
    'Don de la nuit : ',
    'Дар владений ночи: ',
    'Món Quà Dạ Vực - ',
    'Geschenk des Nachtreichs – ',
    'Presente do Reino da Noite: ',
    'Gece Diyarının Armağanı: ',
    'Dono del Reame notturno: ',
    'Moonsign Benediction: ',
    '月兆祝赐·',
    '月兆祝賜·',
    '月兆の祝福·',
    '달빛 징조의 축복·',
    'Bendición presagiolunar: ',
    'Bénédiction de signelune : ',
    'Дар лунного знамения: ',
    'Chúc Phúc Nguyệt Triệu - ',
    'Mondomen-Segen – ',
    'Bênção do Presságio Lunar: ',
    'Ay Sembolü Kutsaması: ',
    'Benedizione del Presagio lunare: ',
    'Witch\'s Eve Rite: ',
    '魔女的前夜礼·',
    '魔女的前夜禮·',
    '魔女からの贈り物・',
    '마녀의 전야제·',
    'Rito de la noche de brujas: ',
    'Veillée de la sorcière : ',
    'Ведьмин ритуал кануна: ',
    'Đêm Lễ Ma Nữ - ',
    'Geschenk der Hexennacht – ',
    'Presente da Noite da Bruxa: ',
    'Cadının Gece Ayini: ',
    'Rito della Vigilia della strega: ',
]


def remove_keywords(in_text):
    for text in REMOVE:
        in_text = in_text.replace(text, '')
    return in_text


def format_ol(texts, fallback='', tl=True, rm=True):
    """An Other Languages template from {language: text}, e.g. composed from several TextMap entries."""
    en_text = texts.get('EN')
    en_text = fallback if en_text is None else en_text
    output = [f'{{{{Other Languages\n|en       = {remove_keywords(en_text)}']

    for lang, key in OUTORDER.items():
        localized_text = texts.get(key)
        localized_text = en_text if localized_text is None else localized_text
        tx = f'|{lang}'.ljust(10) + f'= {remove_keywords(localized_text)}'
        output.append(tx)

        if localized_text == en_text:
            continue
        if rm and lang in ['zhs', 'zht', 'ja', 'ko', 'th']:
            output.append(f'|{lang}_rm'.ljust(10) + '= ')
        if tl and lang != 'zhs':
            if lang == 'zht':
                lang = 'zh'
            output.append(f'|{lang}_tl'.ljust(10) + '= ')

    output.append('}}')
    return '\n'.join(output)


def find_ol_ids(text, source):
    """TextMapHashes matching a hash or an exact, case-insensitive name."""
    if text in source:
        return [text]
    folded = text.casefold()
    return [identifier for identifier, value in source.items() if value.casefold() == folded]


def lookup_ol(text, textmaps, input_lang='EN', tl=True, rm=True):
    """Distinct localization results matching an exact, case-insensitive name or a TextMapHash."""
    source = textmaps[input_lang]
    identifiers = find_ol_ids(text, source)
    results, seen = [], set()
    for identifier in identifiers:
        texts = {lang: values.get(identifier) for lang, values in textmaps.items()}
        key = tuple(texts.get(lang) for lang in ('EN', *OUTORDER.values()))
        if key in seen:
            continue
        seen.add(key)
        results.append({'textmap_hash': identifier, 'text': format_ol(texts, source[identifier], tl, rm)})
    return results
