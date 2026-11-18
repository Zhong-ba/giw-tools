'''The selectable periods of the Spiral Abyss, Stygian Onslaught and Imaginarium Theater tools, read from their
schedule tables. Shared by the tools and the web API, which lists them for the form (newest first).'''
import re
from datetime import datetime, timedelta
import toolLog as report

TIME_FORMAT = '%Y-%m-%d %H:%M:%S'
# A rotation runs from 04:00 on its start day until 03:59:59 on the next one's, which the wiki shows as the day before.
DAY_START = timedelta(hours=4)
# The wiki ends each Stygian Onslaught at 03:59:59 eight days before the data's end time; this held for every event so far.
STYGIAN_WIKI_END = timedelta(days=8)


def opening(schedule):
    '''A TowerScheduleExcelConfigData rotation's start time, or None.'''
    times = [item.get('OpenTime') for item in schedule.get('Schedules') or [] if isinstance(item, dict) and item.get('OpenTime')]
    return datetime.strptime(times[0], TIME_FORMAT) if times else None


def rotations(rows):
    '''Spiral Abyss rotations with a start time, oldest first.'''
    return sorted((row for row in rows if opening(row)), key=opening)


def times(row):
    '''The date-time strings of a LeyLineChallengeExcelConfigData event (start, end), whose columns are scrambled.'''
    return sorted(value for value in row.values() if isinstance(value, str) and re.fullmatch(r'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d', value))


def events(rows):
    '''Stygian Onslaught events with start and end times, oldest first.'''
    return sorted((row for row in rows if len(times(row)) >= 2), key=lambda row: times(row)[0])


def stygian_end(row):
    return (datetime.strptime(times(row)[-1], TIME_FORMAT) - STYGIAN_WIKI_END).replace(hour=3, minute=59, second=59)


def abyss_periods(rows):
    '''[{'value': start date, 'label': ...}] of the Spiral Abyss rotations, newest first.'''
    ordered = rotations(rows)
    result = []
    for index, row in enumerate(ordered):
        start = opening(row)
        following = opening(ordered[index + 1]) if index + 1 < len(ordered) else None
        close = datetime.strptime(row['CloseTime'], TIME_FORMAT) if row.get('CloseTime') else following
        end = f' – {(close - DAY_START).strftime("%Y-%m-%d")}' if close else ''
        result.append({'value': start.strftime('%Y-%m-%d'), 'label': f'{start:%Y-%m-%d}{end}'})
    return result[::-1]


def stygian_periods(rows):
    '''[{'value': start date, 'label': dates, 'name': event name}] of the Stygian Onslaught events, newest first.'''
    result = []
    for row in events(rows):
        name = row.get('ChallengeNameTextMapHash')
        result.append({'value': times(row)[0][:10], 'label': f'{times(row)[0][:10]} – {stygian_end(row):%Y-%m-%d}',
                       **({'name': name} if isinstance(name, str) else {})})
    return result[::-1]


def seasons(rows):
    '''The RoleCombatScheduleExcelConfigData row of each Imaginarium Theater season, oldest first. Test schedules
    reuse a season's character config, so each config counts once at its last schedule, and placeholder schedules
    far in the future are skipped.'''
    latest = {}
    for row in rows:
        found = times(row)
        if found and found[0][:4] < '2099':
            config = row.get('AvatarConfigId')
            if config not in latest or times(latest[config])[0] < found[0]:
                latest[config] = row
    return sorted(latest.values(), key=lambda row: times(row)[0])


def theater_periods(rows):
    '''[{'value': start date, 'label': dates, 'name': 'Season N'}] of the Imaginarium Theater seasons, newest first.'''
    result = []
    for number, row in enumerate(seasons(rows), 1):
        start, end = times(row)[0], times(row)[-1]
        result.append({'value': start[:10], 'label': f'{start[:10]} – {end[:10]}', 'name': f'Season {number}'})
    return result[::-1]


PERIODS = {
    'abyss': ('TowerScheduleExcelConfigData', abyss_periods),
    'stygian': ('LeyLineChallengeExcelConfigData', stygian_periods),
    'theater': ('RoleCombatScheduleExcelConfigData', theater_periods),
}


def wiki_version(date):
    '''The version live on date per the wiki's {{Date to Version}}, or '' if the wiki cannot be reached.'''
    from wikiVersion import date_versions
    try:
        version = date_versions([date]).get(date, '')
    except (OSError, ValueError) as error:
        report.warning(f'Could not look up the version for {date} on the wiki: {error}')
        return ''
    if version:
        report.info(f'Version from the wiki\'s Date to Version for {date}: {version}')
    return version
