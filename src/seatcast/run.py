import importlib
import sys

# step -> module:function; CLI args after the step are passed through positionally
STEPS = {
    'day0': 'io:day0',
    'ingest': 'io:load_tickets',
    'match': 'match:run',
    'flows': 'flows:run',
    'load': 'load:run',
    'checks': 'checks:run',
    'gps': 'checks:gps',
    'note': 'checks:note',
    'plan': 'plan:cli',
    'serve': 'api:serve',
}
PIPE = ['day0', 'ingest', 'match', 'flows', 'load', 'checks']


def step(name, args):
    mod, fn = STEPS[name].split(':')
    getattr(importlib.import_module('seatcast.' + mod), fn)(*args)


def main(argv):
    if not argv or argv[0] not in [*STEPS, 'all']:
        sys.exit('usage: python -m seatcast.run {all|%s} [args]' % '|'.join(STEPS))
    for s in PIPE if argv[0] == 'all' else [argv[0]]:
        print('==', s, flush=True)
        step(s, argv[1:])


if __name__ == '__main__':
    main(sys.argv[1:])
