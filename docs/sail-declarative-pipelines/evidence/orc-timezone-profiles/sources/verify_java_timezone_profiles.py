"""Independent integer-only profile/resolver implementation and oracle verifier.

The verifier does not import zoneinfo, datetime, Jiff, or Java timezone logic.
It replays all retained oracle digests with the documented profile contract.
"""
import argparse
import bisect
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Iterator


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def identity(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def variants(value: int) -> list[str]:
    return [str(value), f'{value:02}'] if value < 10 else [str(value)]


UNKNOWN = [
    '', 'Z', 'UT', 'utc', 'gmt', ' UTC', 'UTC ', 'Not/AZone',
    'America/los_angeles', 'UTC+05:30', '+05:30', '-0530', 'GMT', 'GMT+',
    'GMT-', 'GMT+05:30:15', 'GMT-00:00:01', 'GMT+23:59:59', 'GMT+05:30:00',
    'GMT+00530', 'GMT+24:00', 'GMT+05:60', 'GMT+05:30:60', 'GMT+1:2:03',
    'GMT+01:2:03', 'GMT+1:2', 'GMT+1::03', 'GMT+01:02:03:04',
    'GMT+01:02\n', 'GMT+\0', 'GMT+１２:00',
]


def resolver_cases(names: Iterable[str]) -> Iterator[str]:
    for sign in ['+', '-']:
        for width in range(1, 5):
            for value in range(10**width):
                yield f'GMT{sign}{value:0{width}}'
        for hour in range(24):
            for h in variants(hour):
                for minute in range(60):
                    yield f'GMT{sign}{h}:{minute:02}'
                    for m in variants(minute):
                        for second in range(60):
                            yield f'GMT{sign}{h}:{m}:{second:02}'
        for h in ['', '24', '99', '000', '-1', 'A', '１']:
            for m in ['', '0', '60', '99', '000', '-1', 'B', '０']:
                for s in ['', '0', '60', '99', '000', '-1', 'C', '０']:
                    yield f'GMT{sign}{h}:{m}:{s}'
    yield from UNKNOWN
    for name in sorted(names):
        yield name
        yield name.lower()
        yield name.upper()
        yield ' ' + name


GMT = re.compile(
    r'GMT([+-])(?:([0-9]{1,4})|([0-9]{1,2}):([0-9]{2})|'
    r'([0-9]{1,2}):([0-9]{1,2}):([0-9]{2}))'
)


class Database:
    def __init__(self, data: dict[str, Any]) -> None:
        assert data['format_version'] == 1
        self.data = data
        self.low, self.high = data['configuration']['offset_domain_millis']
        self.histories = {}
        self.cycles = {}
        for key, profile in data['profiles'].items():
            assert key == identity(profile), ('profile identity', key)
            rows = profile['transitions']
            times = [row[0] for row in rows]
            assert all(a < b for a, b in zip(times, times[1:]))
            assert -2**31 <= profile['raw_prefix_offset_millis'] < 2**31
            assert all(-2**31 <= row[1] < 2**31 for row in rows)
            self.histories[key] = times
            future = profile['future']
            if not rows:
                assert future == {'kind': 'fixed', 'offset_millis': profile['raw_prefix_offset_millis']}
            if future['kind'] == 'fixed':
                assert future['offset_millis'] == (rows[-1][1] if rows else profile['raw_prefix_offset_millis'])
            else:
                assert future['kind'] == 'cycle' and rows and future['id'] in data['cycles']
        for key, cycle in data['cycles'].items():
            assert key == identity(cycle), ('cycle identity', key)
            times = [row[0] for row in cycle['rows']]
            assert times[0] == 0
            assert cycle['period_millis'] == 146097 * 86400000
            assert all(a < b for a, b in zip(times, times[1:]))
            assert times[-1] < cycle['period_millis']
            assert all(-2**31 <= row[1] < 2**31 for row in cycle['rows'])
            self.cycles[key] = times
        assert all(zone['profile'] in data['profiles'] for zone in data['zones'].values())

    def offset(self, key: str, millis: int) -> int:
        if not self.low <= millis <= self.high:
            raise ValueError('outside qualified offset domain')
        profile = self.data['profiles'][key]
        times = self.histories[key]
        if not times or millis < times[0]:
            return profile['raw_prefix_offset_millis']
        if millis <= times[-1]:
            return profile['transitions'][bisect.bisect_right(times, millis)-1][1]
        future = profile['future']
        if future['kind'] == 'fixed':
            return future['offset_millis']
        cycle = self.data['cycles'][future['id']]
        position = (millis-cycle['anchor_millis']) % cycle['period_millis']
        return cycle['rows'][bisect.bisect_right(self.cycles[future['id']], position)-1][1]

    def adjustment(self, writer: str, reader: str, millis: int) -> int:
        w, r = self.offset(writer, millis), self.offset(reader, millis)
        return w-self.offset(reader, millis+w-r)

    def resolve(self, name: str) -> tuple[str, int, int]:
        zone = self.data['zones'].get(name)
        if zone is not None:
            key = zone['profile']
            return zone['resolved_id'], self.offset(key, 0), self.data['profiles'][key]['orc_epoch_seconds']
        match = GMT.fullmatch(name)
        if match:
            sign, compact, h, m, hs, ms, s = match.groups()
            if compact is not None:
                hours, minutes = (int(compact), 0) if len(compact) <= 2 else divmod(int(compact), 100)
                seconds = 0
            elif h is not None:
                hours, minutes, seconds = int(h), int(m), 0
            else:
                hours, minutes, seconds = int(hs), int(ms), int(s)
            if hours <= 23 and minutes <= 59 and seconds <= 59:
                offset = (hours*3600+minutes*60+seconds) * (-1 if sign == '-' else 1)
                resolved = f'GMT{sign}{hours:02}:{minutes:02}'
                if seconds:
                    resolved += f':{seconds:02}'
                return resolved, offset*1000, self.data['configuration']['utc_epoch_seconds']-offset
        gmt = self.data['profiles'][self.data['zones']['GMT']['profile']]
        return 'GMT', 0, gmt['orc_epoch_seconds']

    def queries(self, key: str, first_cycle: bool, plan: dict[str, Any]) -> list[int]:
        profile = self.data['profiles'][key]
        points = set(plan['baseline_millis'])
        rows = profile['transitions']
        for index, (millis, _) in enumerate(rows):
            points.update([millis-1, millis, millis+1])
            if index:
                previous = rows[index-1][0]
                points.add(previous+(millis-previous)//2)
        if first_cycle:
            cycle = self.data['cycles'][profile['future']['id']]
            for anchor in plan['cycle_block_starts_millis']:
                for index, (position, _) in enumerate(cycle['rows']):
                    end = cycle['rows'][index+1][0] if index+1 < len(cycle['rows']) else cycle['period_millis']
                    for millis in [anchor+position-1, anchor+position, anchor+position+1, anchor+position+(end-position)//2]:
                        if rows[-1][0] < millis and self.low <= millis <= self.high:
                            points.add(millis)
        return sorted(points)


def update(digest: Any, *fields: object) -> None:
    digest.update(canonical(list(fields)) + b'\n')


def verify(root: Path) -> None:
    artifact = root / 'java-timezone-profiles.json'
    encoded = artifact.read_bytes()
    data = json.loads(encoded)
    assert encoded == canonical(data) + b'\n', 'non-canonical artifact'
    db = Database(data)
    plan = json.loads((root/'java-timezone-profile-verification.json').read_text())
    resolver_oracle = json.loads((root/'java-timezone-resolver-oracle.json').read_text())
    offset_digest, conversion_digest = hashlib.sha256(), hashlib.sha256()
    seen = set()
    offset_checks = conversion_checks = 0
    utc = data['zones']['UTC']['profile']
    for name, zone in sorted(data['zones'].items()):
        key = zone['profile']
        future = data['profiles'][key]['future']
        first = future['kind'] == 'cycle' and future['id'] not in seen
        if future['kind'] == 'cycle':
            seen.add(future['id'])
        points = db.queries(key, first, plan)
        assert {'offset_checks': len(points), 'full_cycle_checked': first} == plan['per_zone'][name]
        for millis in points:
            update(offset_digest, name, millis, db.offset(key, millis))
            offset_checks += 1
        for millis in plan['baseline_millis']:
            if millis < db.low+2**32 or millis > db.high-2**32:
                continue
            update(conversion_digest, name, millis, db.adjustment(utc, key, millis), db.adjustment(key, utc, millis))
            conversion_checks += 2
    assert offset_checks == plan['offset_checks']
    assert offset_digest.hexdigest() == plan['offset_oracle_sha256'], 'offset oracle mismatch'
    assert conversion_checks == plan['orc_conversion_checks']
    assert conversion_digest.hexdigest() == plan['orc_conversion_oracle_sha256'], 'ORC oracle mismatch'
    resolver_digest = hashlib.sha256()
    resolver_count = 0
    for name in resolver_cases(data['zones']):
        resolved, offset, epoch = db.resolve(name)
        update(resolver_digest, name, resolved, offset, epoch)
        resolver_count += 1
    assert resolver_count == resolver_oracle['case_count']
    assert resolver_digest.hexdigest() == resolver_oracle['oracle_sha256'], 'resolver oracle mismatch'
    for name, example in resolver_oracle['examples'].items():
        resolved, offset, epoch = db.resolve(name)
        assert example == {'resolved_id': resolved, 'offset_at_unix_epoch_millis': offset, 'orc_epoch_seconds': epoch}
    result = {
        'scope': 'Independent integer-only Python reader/resolver versus all retained public Java oracle digests',
        'profile_sha256': hashlib.sha256(encoded).hexdigest(),
        'offset_checks': offset_checks, 'orc_conversion_checks': conversion_checks,
        'resolver_cases': resolver_count, 'profile_identity_checks': len(data['profiles']),
        'cycle_identity_checks': len(data['cycles']), 'failures': 0,
    }
    (root/'independent-verification.json').write_bytes(canonical(result)+b'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    verify(parser.parse_args().directory)
