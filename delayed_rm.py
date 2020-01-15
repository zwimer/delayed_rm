#!/usr/bin/env python3
from multiprocessing import Process

import tempfile
import shutil
import time
import sys
import os


# Config
log_f = '/tmp/delay_rm.log'
d_time = 900


def print_log():
    try:
        with open(log_f) as f:
            outs = f.read() + '\n'
    except FileNotFoundError:
        outs = ''
    outs += 'log file: ' + log_f
    print(outs)

def parse_args(args):
    assert args, 'Error: no arguments'
    if args[0] == ('--log'):
        print_log()
        sys.exit(0)
    try:
        return unsafe_parse_args(args)
    except AssertionError as err:
        print(err)
        sys.exit(1)

def unsafe_parse_args(args):
    _f = False
    _r = False
    _rf = False
    rf_f = set([ '-rf', '-fr' ])
    f_f = set(['-f']) | rf_f
    r_f = set(['-r']) | rf_f
    valid = f_f | r_f
    items = set()
    any_dirs = False
    for i in args:
        if i.startswith('-'):
            assert i in valid, 'Error: delay_rm only supports -rf'
            if i in r_f: _r = True
            if i in f_f: _f = True
        else:
            add = os.path.realpath(i)
            assert os.path.exists(add), 'Error: ' + add + ' is not a file or directory'
            any_dirs |= os.path.isdir(add)
            items.add(add)
    assert len(items) > 0, 'Error: Nothing to remove'
    if _r or _f:
        assert _r and _f, 'Error: delay_rm does not support -f or -r without the other'
        _rf = True
    else:
        assert any_dirs == False, 'Error: no dirs allowed without -rf'
    return (_rf, items)

def delay_rm(del_dir):
    die = True
    time.sleep(d_time)
    f = shutil.rmtree(del_dir)

def main(_, *args):
    assert os.path.exists(os.path.dirname(log_f)), \
        'log file enclosing directory does not exist'

    # Arg parse
    rf, files = parse_args(args)

    # Move files
    outd = tempfile.mkdtemp()
    names = list(files)
    for f in names:
        try:
            shutil.move(f, outd)
            files.remove(f)
        except Exception as err:
            print(err)
            pass
    if len(files) > 0:
        print('Error: failed to rm:\n' + '\n'.join(files))
        raise

    # Note location
    msg = '\n* delay_rm' + (' -rf' if rf else '') + ':'
    msg += ' \n*\t' + ' \n*\t'.join(names)
    msg += ' \n* Files temporarily stored in:\n' + outd + '\n'
    try:
        with open(log_f, 'a') as f:
            f.write(msg)
    except:
        msg = 'Error: could not log delay dir in ' + log_f + '\nInfo:\n' + msg
        print(msg)

    # Delay delete files
    p = Process(target=delay_rm, args=(outd,))
    p.start()

    # Die but do not kill child
    os._exit(0)

if __name__ == '__main__':
    main(*sys.argv)
