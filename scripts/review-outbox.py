"""Read-only operational diagnostic for the worker outbox.

It intentionally prints only an allow-list of event fields. It never changes a
lease, retries an event, or exposes the stored request payload.
"""
import argparse
import json
from pathlib import Path
import sqlite3

parser = argparse.ArgumentParser()
parser.add_argument('--database', default=str(Path(__file__).resolve().parent.parent / 'vision-worker/data/events.sqlite3'))
parser.add_argument('--status', choices=('pending', 'rejected', 'all'), default='rejected')
parser.add_argument('--json', action='store_true', dest='as_json')
args = parser.parse_args()
database = Path(args.database).resolve()
with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
    where = '' if args.status == 'all' else 'WHERE rejected=?'
    values = () if args.status == 'all' else (args.status == 'rejected',)
    rows = []
    for sequence, event_id, payload_json, attempts, available_at, rejected, error in connection.execute(
        f'SELECT sequence,event_id,payload,attempts,available_at,rejected,error FROM outbox {where} ORDER BY sequence', values):
        payload = json.loads(payload_json)
        rows.append({
            'sequence': sequence,
            'eventId': event_id,
            'status': 'rejected' if rejected else 'pending',
            'attempts': attempts,
            'availableAtUnix': available_at,
            'error': error,
            # The event identity and occurrence data are evidence, not secrets.
            'cameraId': payload.get('cameraId'),
            'roundId': payload.get('roundId'),
            'crossedAt': payload.get('crossedAt'),
        })
    if args.as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            print(' | '.join(str(row[key] if row[key] is not None else '') for key in
                             ('sequence', 'eventId', 'status', 'attempts', 'crossedAt', 'cameraId', 'roundId', 'error')))
