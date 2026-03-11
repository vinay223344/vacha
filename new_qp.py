#!/usr/bin/env python3
import sys
import os
import re
import shutil

# -------------------------------------------------
# 1. Check Command Line Argument
# -------------------------------------------------
if len(sys.argv) != 2:
    print("Required number of command line arguments are not provided!")
    sys.exit(1)

verilog_file = sys.argv[1]

# -------------------------------------------------
# 2. Check if Verilog file exists
# -------------------------------------------------
if not os.path.exists(verilog_file):
    print("The provided Verilog file does not exist!")
    sys.exit(1)

# -------------------------------------------------
# 3. Create / Handle WORKDIR
# -------------------------------------------------
workdir = "./WORKDIR"

if os.path.exists(workdir):
    ans = input("WORKDIR already exists. Overwrite? (Y/N): ")
    if ans.lower() != 'y':
        print("Exiting script.")
        sys.exit(0)
    shutil.rmtree(workdir)

os.makedirs(workdir)

# -------------------------------------------------
# 4. Read File and Remove Comments
# -------------------------------------------------
with open(verilog_file, 'r') as f:
    code = f.read()

# Remove multiline comments
code = re.sub(r'/\*.*?\*/', '', code, flags=re.S)

# Remove single line comments
code = re.sub(r'//.*', '', code)

lines = code.split('\n')

# -------------------------------------------------
# 5. Initialize Variables
# -------------------------------------------------
inputs = []
outputs = []
inouts = []
ports = set()

instances = {}
compile_errors = []

top_module = None

# -------------------------------------------------
# 6. Extract Top Module Name
# -------------------------------------------------
for i, line in enumerate(lines):
    m = re.search(r'\bmodule\s+(\w+)', line)
    if m:
        top_module = m.group(1)
        break

if not top_module:
    compile_errors.append((0, "ERR03: missing module declaration"))
    top_module = "UNKNOWN_MODULE"

# -------------------------------------------------
# 7. Module Header Checks (ERR07, ERR10)
# -------------------------------------------------
for i, line in enumerate(lines):
    if 'module' in line:
        # ERR07 trailing comma
        if re.search(r'module\s+\w+\s*\([^)]*,\s*\)', line):
            compile_errors.append((i+1, f"ERR07: comma misuse in port list in module definition in line {i+1}"))

        # ERR10 missing comma
        if re.search(r'module\s+\w+\s*\([^)]*\w+\s+\w+[^,)]*\)', line):
            compile_errors.append((i+1, f"ERR10: missing comma between ports in module definition in line {i+1}"))

# -------------------------------------------------
# 8. Parse Ports (supports multiline)
# -------------------------------------------------
buffer = ""
start_line = 0

port_decl = re.compile(r'\b(input|output|inout)\b')

for i, line in enumerate(lines):
    if port_decl.search(line):
        buffer = line.strip()
        start_line = i+1

        while ';' not in buffer and i+1 < len(lines):
            i += 1
            buffer += ' ' + lines[i].strip()

        stmt = buffer

        # ERR09 case sensitivity
        if re.search(r'\bInput\b|\bOutput\b|\bInout\b', stmt):
            compile_errors.append((start_line, f"ERR09: case sensitivity issue of port direction in line {start_line}"))

        # ERR08 multiple widths
        if re.search(r'\[[^\]]+\]\s*\[[^\]]+\]', stmt):
            compile_errors.append((start_line, f"ERR08: multiple widths on same port in line {start_line}"))

        # ERR01 missing semicolon
        if not stmt.strip().endswith(';'):
            compile_errors.append((start_line, f"ERR01: missing semicolon ';' in line {start_line}"))
            continue

        m = re.search(r'(input|output|inout)\s*(\[[^\]]+\])?\s*(.*);', stmt)
        if not m:
            continue

        direction = m.group(1)
        width = m.group(2) if m.group(2) else "1"
        names = m.group(3).split(',')

        for name in names:
            name = name.strip()

            # ERR04 illegal name
            if not re.match(r'^[A-Za-z_]\w*$', name):
                compile_errors.append((start_line, f"ERR04: illegal port name {name} in line {start_line}"))
                continue

            # ERR05 duplicate port
            if name in ports:
                compile_errors.append((start_line, f"ERR05: duplicate port name {name} in line {start_line}"))
                continue

            ports.add(name)

            if direction == "input":
                inputs.append((name, width))
            elif direction == "output":
                outputs.append((name, width))
            else:
                inouts.append((name, width))

# -------------------------------------------------
# 9. ERR06 Missing Direction
# -------------------------------------------------
for i, line in enumerate(lines):
    if re.search(r'^\s*\[[^\]]+\]\s*[A-Za-z_]\w*\s*;', line):
        compile_errors.append((i+1, f"ERR06: missing direction for the port in line {i+1}"))

# -------------------------------------------------
# 10. Submodule Instantiations
# -------------------------------------------------
inst_pattern = r'^\s*(?!module\b|always\b|if\b|for\b|case\b)(\w+)\s+(\w+)\s*\('

for i, line in enumerate(lines):
    m = re.search(inst_pattern, line)
    if m:
        cell = m.group(1)
        inst = m.group(2)

        # ERR04 illegal instance name
        if not re.match(r'^[A-Za-z_]\w*$', inst):
            compile_errors.append((i+1, f"ERR04: illegal instance name {inst} in line {i+1}"))
            continue

        # ERR11 duplicate instance
        if inst in instances:
            compile_errors.append((i+1, f"ERR11: Instance name {inst} is already defined in line {i+1}"))
        else:
            instances[inst] = cell

# -------------------------------------------------
# 11. ERR02 Unmatched Parenthesis (global)
# -------------------------------------------------
if code.count('(') != code.count(')'):
    compile_errors.append((0, "ERR02: missing parenthesis in file"))

# -------------------------------------------------
# 12. ERR03 begin-end / module-endmodule
# -------------------------------------------------
begin_count = len(re.findall(r'\bbegin\b', code))
end_count = len(re.findall(r'\bend\b', code))
module_count = len(re.findall(r'\bmodule\b', code))
endmodule_count = len(re.findall(r'\bendmodule\b', code))

if begin_count != end_count or module_count != endmodule_count:
    compile_errors.append((0, "ERR03: missing endmodule/end for the module/always block"))

# -------------------------------------------------
# 13. Create Directory Structure
# -------------------------------------------------
top_dir = os.path.join(workdir, top_module)
os.makedirs(top_dir)

# -------------------------------------------------
# 14. Write Port Files
# -------------------------------------------------
with open(os.path.join(top_dir, "inputs"), "w") as f:
    for name, width in inputs:
        f.write(f"{name}, {width}\n")

with open(os.path.join(top_dir, "outputs"), "w") as f:
    for name, width in outputs:
        f.write(f"{name}, {width}\n")

with open(os.path.join(top_dir, "inouts"), "w") as f:
    for name, width in inouts:
        f.write(f"{name}, {width}\n")

# -------------------------------------------------
# 15. Write Submodules (unique instances)
# -------------------------------------------------
with open(os.path.join(top_dir, "submodules"), "w") as f:
    for inst, cell in instances.items():
        f.write(f"{cell}, {inst}\n")

# -------------------------------------------------
# 16. Write compile.log (sorted by line number)
# -------------------------------------------------
compile_errors.sort(key=lambda x: x[0])

with open(os.path.join(workdir, "compile.log"), "w") as f:
    for _, msg in compile_errors:
        f.write(msg + "\n")

# -------------------------------------------------
# 17. Done
# -------------------------------------------------
print("Parsing completed.")
print("Check WORKDIR for outputs.")