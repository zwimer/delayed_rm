# delayed\_rm
Ever wish you had a few minutes to undo an rm? Now you do! 

# Usage

Just like `rm`. Supports `-r` and `-f` flags when used together. Passing `--delay` allows users to specify the delay. Passing `--log` will print log information

# Examples

1. `rm foo bar`
1. `rm -rf dir1 dir2`
1. `rm --delay 3600 baz`
1. `rm --log`
