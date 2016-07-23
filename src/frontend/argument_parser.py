#!/usr/bin/env python3

import argparse
import ast
import os.path as path
import sys
import re

import ian_utils as iu

from lexed_to_parsed import parse_function
from pass_lift_inputs import lift_inputs
from pass_lift_consts import lift_consts
from pass_lift_assign import lift_assign
#from pass_pow import pow_replacement
#from pass_div_zero import div_by_zero
from output_rust import to_rust
from output_interp import to_interp

from input_parser import process

def parse_args():
    exe = path.basename(sys.argv[0])
    arg_parser = create_common_option_parser(exe == "gelpia")

    if exe == "dop_gelpia":
        (args, function, epsilons) = add_dop_args(arg_parser)
    else:
        if exe != "gelpia":
            print("Defaulting to gelpia argument parsing")
        (args, function, epsilons) = add_gelpia_args(arg_parser)
        
    return finish_parsing_args(args, function, epsilons)





def create_common_option_parser(use_ampersand):
    arg_parser = iu.IanArgumentParser(description="Global function optimizer based "
                                      "on branch and bound for noncontinuous "
                                      "functions.",
                                      fromfile_prefix_chars= '@' if use_ampersand else None)
    arg_parser.add_argument("-v", "--verbose", help="increase output verbosity",
                            type=int, default=0)    
    arg_parser.add_argument("-d", "--debug",
                        help="Debug run of function. Makes the minimum verbosity"
                        " level one. Runs a debug build of gelpia, "
                        "with backtrace enabled.", action="store_true")
    arg_parser.add_argument("--dreal", action='store_const', const=True, default=False)
    arg_parser.add_argument("-t", "--timeout",
                        type=int, help="Timeout for execution in seconds.",
                        default=0)
    arg_parser.add_argument("-s", "--seed",
                        type=int, help="Optional seed (u32) for the random number generators used within gelpia.\n"
                            "A value of 0 (default) indicates to use the default seed, a value of 1 indicates gelpia \n"
                            "will use a randomly selected seed. Any other value will be used as the RNG seed.",
                            default=0)
    arg_parser.add_argument("-M", "--maxiters",
                        type=int, help="Maximum IBBA iterations.",
                        default=0)
    arg_parser.add_argument("-g", "--grace",
                        type=int, help="Grace period for timeout option. Defaults to twice the supplied timeout",
                        default=0)
    arg_parser.add_argument("-u", "--update",
                        type=int, help="Time between update thread executions.",
                            default=0)
    arg_parser.add_argument("-L", "--logging",
                        help="Enable solver logging to stderr",
                        type=str, nargs='?', const=True, default=None)
    arg_parser.add_argument("-T", "--fptaylor",
                        help="FPTaylor compatibility",
                            type=str, nargs='?', const=True, default=False)
    arg_parser.add_argument("-z", "--skip-div-zero",
                            action="store_true", help="Skip division by zero check")    
    arg_parser.add_argument("-ie", "--input-epsilon",
                        help="cuttoff for function input size",
                            type=float, default=None)
    arg_parser.add_argument("-oer", "--relative-input-epsilon",
                            help="relative error cutoff for function output size",
                            type=float, default=None);
    arg_parser.add_argument("-oe", "--output-epsilon",
                        help="cuttoff for function output size",
                            type=float, default=None)
    return arg_parser




def parse_input_box(box):
    reformatted = list()
    names = set()
    for i in box:
      name = i[0]
      if name in names:
        print("Duplicate variable", name)
        exit(-1)
      names.add(name)
      reformatted.append("{} = [{},{}];".format(name, *i[1]))
    return '\n'.join(reformatted)

def add_gelpia_args(arg_parser):
    """ Command line argument parser. Returns a dict from arg name to value"""

    arg_parser.add_argument("-i", "--input",
                        help="Search space. "
                        "Format is: {V1 : (inf_V1, sup_V1), ...}"
                        "Where V1 is the interval name, inf_V1 is the infimum, "
                        "and sup_V1 is the supremum",
                        type=str, nargs='+', required=True,)
    arg_parser.add_argument("-f", "--function",
                        help="the c++ interval arithmatic function to evaluate",
                        type=str, nargs='+', required=True,)


    
    # actually parse
    args = arg_parser.parse_args()

    # reformat query
    function = ' '.join(args.function)
    if args.dreal:
        function = "-({})".format(function)

    inputs = ' '.join(args.input)
    start = parse_input_box(process(inputs))

    reformatted_query = start+'\n'+function

    ie = oe = 0.001
    oer = 0
    if args.input_epsilon != None:
        ie = args.input_epsilon
    if args.output_epsilon != None:
        oe = args.output_epsilon
    if args.output_epsilon != None:
        oe = args.output_epsilon
    if args.relative_input_epsilon != None:
        oer = args.relative_input_epsilon
    return (args,
            reformatted_query,
            [ie, oe, oer])





def add_dop_args(arg_parser):
    arg_parser.add_argument("query_file",type=str)
    arg_parser.add_argument("-p", "--prec",
                        help="dOp delta precision",
                            type=float, default=None)
    args = arg_parser.parse_args()
    with open(args.query_file, 'r') as f:
        query = f.read()

        
    # precision
    pmatch = re.match(r"^prec: +(\d*.\d*) *$", query)
    iematch = re.match(r"^ie: +(\d*.\d*) *$", query)
    oematch = re.match(r"^oe: +(\d*.\d*) *$", query)
    oermatch = re.match(r"^oer: +(\d*.\d*) *$", query)
    ie = oe = 0.001
    oer = 0
    # overide values with file values
    if pmatch:
        ie = oe = float(pmatch.group(1))
    if iematch:
        ie = float(iematch.group(1))
    if oematch:
        oe = float(oematch.group(1))
    if oermatch:
        oer = float(oermatch.group(1))
    #overide those with command line values
    if args.prec != None:
        ie = oe = args.prec
    if args.input_epsilon != None:
        ie = args.input_epsilon
    if args.output_epsilon != None:
        oe = args.output_epsilon
    if args.output_epsilon != None:
        oe = args.output_epsilon
    if args.relative_input_epsilon != None:
        oer = args.relative_input_epsilon


        
    # vars
    lines = [line.strip() for line in query.splitlines() if line.strip()!=''and line.strip()[0] != '#']
    try:
        start = lines.index("var:")
    except:
        print("Malformed query file, no var section: {}".format(args.query_file))
        sys.exit(-1)
    var_lines = list()
    names = set()
    for line in lines[start+1:]:
        if ':' in line:
            break
        match = re.search(r"(\[[^,]+, *[^\]]+\]) *([^;]+)", line)
        if match:
            val = match.group(1)
            name = match.group(2)
            if name in names:
                print("Duplicate variable definition {}".format(name))
                sys.exit(-1)
            names.add(name)
        else:
            print("Malformed query file, imporoper var: {}".format(line))
            sys.exit(-1)
        var_lines.append("{} = {};".format(name, val))
    var_lines = '\n'.join(var_lines)
        
    # cost
    try:
        start = lines.index("cost:")
    except:
        print("Malformed query file, no cost section: {}".format(args.query_file))
        sys.exit(-1)
    function = list()
    for line in lines[start+1:]:
        if ':' in line:
            break
        function.append("({})".format(line.replace(';','')))
    function = '+'.join(function)
    if args.dreal:
        function = "-({})".format(function)
    
    # constraints
    try:
        start = lines.index("ctr:")
    except:
        start = False

    constraints = list()
    if start:
        for line in lines[start+1:]:
            if ':' in line:
                break
            constraints.append(line)
        print("Gelpia does not currently handle constraints")
        sys.exit(-1)

    constraints = '\n'.join(constraints)

    # combining and parsing
    reformatted_query = '\n'.join((var_lines, constraints, function))

    return (args, reformatted_query, [ie, oe, oer])




def finish_parsing_args(args, function, epsilons):
    if args.debug or args.verbose:
        iu.set_log_level(max(1, args.verbose))

    exp = parse_function(function)
    inputs = lift_inputs(exp)
    consts = lift_consts(exp, inputs)
    assign = lift_assign(exp, inputs, consts)
    # IB I'm leaving these commented out. We need to vet them and put them back in
    #    pow_replacement(exp, inputs, consts, assign)

    #    divides_by_zero = div_by_zero(exp, inputs, consts, assign)
    
    #    if divides_by_zero:
    #        print("ERROR: Division by zero")
    #        sys.exit(-2)

    rust_func, new_inputs, new_consts = to_rust(exp, consts, inputs, assign)
    interp_func = to_interp(exp, consts, inputs, assign)
    
    return {"input_epsilon"      : epsilons[0],
            "output_epsilon"     : epsilons[1],
            "rel_output_epsilon" : epsilons[2],
            "inputs"             : new_inputs,
            "constants"          : '|'.join(new_consts),
            "rust_function"      : rust_func,
            "interp_function"    : interp_func,
            "expression"         : exp,
            "debug"              : args.debug,
            "timeout"            : args.timeout,
            "grace"              : args.grace,
            "update"             : args.update,
            "logfile"            : args.logging,
            "dreal"              : args.dreal,
            "fptaylor"           : args.fptaylor,
            "iters"              : args.maxiters,
            "seed"               : args.seed,}
