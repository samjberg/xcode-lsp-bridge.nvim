import os, sys, subprocess, shlex

def is_flag(arg:str) -> bool:
    return arg.startswith('-')

def is_long_flag(arg:str) -> bool:
    return arg.startswith('--') and (arg != '--')

def is_short_flag(arg:str):
    return is_flag(arg) and not is_long_flag(arg) and (arg != '--')

def normalize_args(args: list[str]) -> list[str]:
    if args == sys.argv:
        return args[1:]
    return args

def _get_long_flags(args: list[str], respect_separator=True) -> list[str]:
    if respect_separator:
        if '--' in args:
            args = args[:args.index('--')]
    return [arg for arg in args if is_long_flag(arg)]

def _get_short_flags(args: list[str], respect_separator=True) -> list[str]:
    if respect_separator:
        if '--' in args:
            args = args[:args.index('--')]
    return [arg for arg in args if is_short_flag(arg)]





def parse_args(args: list[str] = [], respect_separator=True) -> dict[str, dict]:
    '''Parses args (sys.argv should be passed in as args)'''
    if '--' in args:
        args = args[:args.index('--')]
    args = normalize_args(args) if args else normalize_args(sys.argv)
    long_flags = _get_long_flags(args, respect_separator)
    short_flags = _get_short_flags(args, respect_separator)
    plain_args = [arg for arg in args if not arg in set(long_flags).union(short_flags)]

    for i, val in enumerate(args):
        if respect_separator and (val == '--'):
            break
        if (val in short_flags) or (val in long_flags):
            last_flag_idx = i

    dct = {'long': {}, 'short': {}, 'args': plain_args, 'argv': args}
    for flag_name in long_flags:
        if '=' in flag_name:
            dct['long'][flag_name[2:]] = flag_name.split('=')[1]
            continue
        val_idx = args.index(flag_name) + 1
        #adding 1 again here is NOT a mistake.  The point is that if we have a situation like: "basecommand -shortarg shortargval -shortarg2 --longarg final_arg"
        #we don't want final_arg to be interpreted as the argument for --longarg, thus adding 1 twice
        if (val_idx) < len(args):
            flag_val = args[val_idx]
            if not is_flag(flag_val):
                dct['long'][flag_name[2:]] = flag_val
                if flag_val in dct['args']:
                    dct['args'].remove(flag_val)
            else:
                dct['long'][flag_name[2:]] = None
        else:
            dct['long'][flag_name[2:]] = None

    for flag_name in short_flags:
        if '=' in flag_name:
            dct['short'][flag_name[1:]] = flag_name.split('=')[1]
            continue
        val_idx = args.index(flag_name) + 1
        #adding 1 again here is NOT a mistake.  The point is that if we have a situation like:
        #basecommand -shortarg shortargval -shortarg2 --shortarg final_arg
        #we don't want final_arg to be interpreted as the argument for --shortarg, thus adding 1 twice
        if (val_idx) < len(args):
            flag_val = args[val_idx]
            if not is_flag(flag_val):
                dct['short'][flag_name[1:]] = flag_val
                if flag_val in dct['args']:
                    dct['args'].remove(flag_val)
            else:
                dct['short'][flag_name[1:]] = None
        else:
            dct['short'][flag_name[1:]] = None

    to_remove = []
    for i, arg in enumerate(plain_args):
        if is_short_flag(arg):
            if (i+1) < len(args):
                dct['short'][arg[1:]] = plain_args[i+1]
            else:
                dct['short'][arg[1:]] = None
            to_remove.append(arg)

        elif is_long_flag(arg):
            if (i+1) < len(args):
                dct['long'][arg[2:]] = plain_args[i+1]
            else:
                dct['long'][arg[2:]] = None
            to_remove.append(arg)
        elif arg == '--':
            to_remove.append(arg)


    for arg in to_remove[::-1]:
        dct['args'].remove(arg)



    return dct




if __name__ == '__main__':
    args = sys.argv[1:]
    if not args:
        raise RuntimeError('Error, must provide path at which to generate git repo')

    path = args[-1]
    all_flags = set([arg for arg in args if arg.startswith('-')])
    long_flags = [arg for arg in all_flags if arg.startswith('--')]
    short_flags = list(all_flags.difference(set(long_flags)))
    non_flags = list(set(args).difference(all_flags))


    dct = parse_args(args)


    print(f"plainargs: {dct['args']}")
    # flags = dct['flags']
    long_dct:dict = dct['long']
    short_dct:dict = dct['short']
    
    print('long args:')
    for key, val in long_dct.items():
        print(f"--{key}: {val}")


    print('short args:')
    for key, val in short_dct.items():
        print(f"-{key}: {val}")



