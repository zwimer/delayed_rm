#!/usr/bin/env python3
from multiprocessing import Process

import argparse
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

# Print to stderr
def eprint(*args):
    print(*args, file=sys.stderr)

# Print the log information
def print_log():
    try:
        with open(log_f) as f:
            outs = f.read()
    except FileNotFoundError:
        outs = ''
    outs += 'log file: ' + log_f
    eprint(outs)

# Parse arguments, print and error if something went wrong.
def validate_files(files, rf):
    files = [ os.path.abspath(i) for i in files ]
    assert len(files) == len(set(files)), 'duplicate items passed'
    assert len(files) == len(set([os.path.basename(i) for i in files])),\
        'Files of same basename has yet to be implemented'
    for i in files:
        assert os.path.lexists(i), i + ' is not a file or directory'
        if not rf:
            assert (not os.path.isdir(i)) or os.path.islink(i), \
                i + ' is a directory. -rf required!'

# Sleep for a while then delete del_dir
def delay_rm(del_dir):
    die = True
    time.sleep(d_time)
    f = shutil.rmtree(del_dir)

# Create the delayed deletion process then die
def die_and_delay_del(del_dir, rc):
    p = Process(target=delay_rm, args=(del_dir,))
    p.start()
    # Die but do not kill child
    os._exit(rc)

# Write a log
def write_log(msg):
    try:
        with open(log_f, 'a') as f:
            f.write(msg + '\n')
            return True
    except:
        eprint('Error: could not log delay dir in ' + log_f + '\nInfo:\n' + msg)
        return False

# Real rm
def rm_r(f):
    assert os.path.exists(f), f + ' does not exist'
    if os.path.isdir(f) and not os.path.islink(f):
        shutil.rmtree(f)
    else:
        os.remove(f)

# Main function
def delayed_rm(files, log, rf, now):
    if log:
        print_log()
        sys.exit(0)
    validate_files(files, rf)
    assert os.path.exists(os.path.dirname(log_f)), \
        'log file enclosing directory does not exist'

    # Output location
    os.makedirs(temp_d_location, mode=0o777, exist_ok=True)

    # Move files into a temp directory
    if not now:
        outd = tempfile.mkdtemp(dir=temp_d_location)
        os.chmod(outd, 0o700)
    success = []
    failed = []
    for f in files:
        try:
            if now:
                rm_r(f)
            else:
                shutil.move(f, outd)
            success.append(f)
        except Exception as err:
            failed.append(f)
            eprint(err)
            pass

    # Inform user of failures
    if len(failed) > 0:
        eprint('Error: failed to rm:\n' + '\n'.join(failed))

    # Log result
    delim = '\n    - '
    msg = ('Real rm' if now else outd) + '\n'
    flags = (('-rf' if rf else '') + ' ' + ('--now' if now else '')).strip()
    msg += '  Flags: ' + (flags if len(flags) else 'None') + '\n'
    msg += '  Succeeded:'
    msg += (' None' if len(success) == 0 else (delim + delim.join(success))) + '\n'
    msg += '  Failed:'
    msg += (' None' if len(failed) == 0 else (delim + delim.join(failed))) + '\n'
    log_success = write_log(msg)

    # Delay rm and die
    rc = int(not log_success | len(failed) > 0)
    if not now:
        die_and_delay_del(outd, rc)
    return rc

def parse_args(prog, args):
    parser = argparse.ArgumentParser(prog=os.path.basename(prog))
    parser.add_argument('-r', action='store_true', default=False)
    parser.add_argument('-f', action='store_true', default=False)
    parser.add_argument('-l', '--log', action='store_true', default=False)
    parser.add_argument('--now', action='store_true', default=False)
    parser.add_argument('files', nargs='*')
    return parser.parse_args(args)

def main(prog, args):
    ns = parse_args(prog, args)
    try:
        if ns.log:
            assert len(args) == 1, '--log may not be used with other arguments'
        else:
            assert len(ns.files) > 0, 'Error: No files passed'
        assert ns.r == ns.f, 'Error: -r and -f must be used together.'
        return delayed_rm(ns.files, ns.log, ns.r and ns.f, ns.now)
    except AssertionError as msg:
        eprint('Error: ' + str(msg))
        return -1


# Don't run on imports
if __name__ == '__main__':
    sys.exit(main(sys.argv[0], sys.argv[1:]))
