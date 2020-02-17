#!/usr/bin/env python3
from multiprocessing import Process

import tempfile
import shutil
import time
import sys
import os


# Config
log_f = os.path.expanduser('~/.delay_rm.log')
temp_d_location = '/tmp/delayed_rm_tmp/'
d_time = 900

# usage: Just like rm
# Supports: -rf
# --log will print log information


# Print the log information
def print_log():
    try:
        with open(log_f) as f:
            outs = f.read() + '\n'
    except FileNotFoundError:
        outs = ''
    outs += 'log file: ' + log_f
    print(outs)

# Parse arguments, print and error if something went wrong.
def parse_and_validate_args(args):
    if len(args) == 0:
        print('Error: no arguments')
        sys.exit(1)
    if args[0] == ('--log'):
        print_log()
        sys.exit(0)
    try:
        return unsafe_parse_and_validate_args(args)
    except AssertionError as err:
        print(err)
        sys.exit(1)

# Parse arguments
# Throw an error if argument parsing fails or argument validation fails
def unsafe_parse_and_validate_args(args):
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
            # Ensure only -r, -f, -rf or -fr were passed as flags
            assert i in valid, 'Error: delay_rm only supports -rf'
            if i in r_f: _r = True
            if i in f_f: _f = True
        else:
            # Ensure any passed files exist
            add = os.path.realpath(i)
            assert os.path.exists(add), 'Error: ' + add + ' is not a file or directory'
            any_dirs |= os.path.isdir(add)
            items.add(add)
    # Ensure files were passed
    assert len(items) > 0, 'Error: Nothing to remove'
    # Ensure -r and -f were both used
    if _r or _f:
        assert _r and _f, 'Error: delay_rm does not support -f or -r without the other'
        _rf = True
    else:
        # Ensure no directories were requested to be deleted without -rf
        assert any_dirs == False, 'Error: no dirs allowed without -rf'
    # Return if -rf was used and a set of items to delete
    return (_rf, items)

# Sleep for a while then delete del_dir
def delay_rm(del_dir):
    die = True
    time.sleep(d_time)
    f = shutil.rmtree(del_dir)

# Create the delayed deletion process then die
def die_and_delay_del(del_dir, code):
    p = Process(target=delay_rm, args=(del_dir,))
    p.start()
    # Die but do not kill child
    os._exit(code)

# Main function
def main(path, *args):
    os.makedirs(temp_d_location, mode=0o777, exist_ok=True)

    basename = os.path.basename(path)
    assert os.path.exists(os.path.dirname(log_f)), \
        'log file enclosing directory does not exist'
    code = 0

    # Arg parse
    rf, files = parse_and_validate_args(args)

    # Move files into a temp directory
    outd = tempfile.mkdtemp(dir=temp_d_location)
    os.chmod(outd, 0o700)
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
        code = 1
    if len(files) == len(names):
        sys.exit(1)

    # Note location
    msg = '\n* ' + basename + (' -rf' if rf else '') + ':'
    msg += ' \n*\t' + ' \n*\t'.join(set(names) - files)
    msg += ' \n* Files temporarily stored in:\n' + outd + '\n'
    try:
        with open(log_f, 'a') as f:
            f.write(msg)
    except:
        msg = 'Error: could not log delay dir in ' + log_f + '\nInfo:\n' + msg
        print(msg)
        code = 1

    # Delay rm and die
    die_and_delay_del(outd, code)


# Don't run on imports
if __name__ == '__main__':
    main(*sys.argv)
