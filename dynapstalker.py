#!/usr/bin/env python

# Read the ASCII log file output from DynamoRIO's drcov utility, converting
# the matched blocks to an IDC script to colorize the blocks in IDA Pro.
#
# Uses code from Pedram Amini's Paimei tool https://github.com/OpenRCE/paimei
# GPLv2 licensed, not by choice but because that's what Pedram used for Paimei
#
# Joshua Wright, josh@wr1ght.net, @joswr1ght

import sys
import re
import pdb

if len(sys.argv) < 4:
    print("Usage: %s drcov-log-file process-name output-idc-script [0xrrggbb color]\n" % sys.argv[0])
    sys.exit(1)

if len(sys.argv) == 5:
    if (len(sys.argv[4]) == 8) and (sys.argv[4][0:2].lower() == "0x"):
        color = sys.argv[4]
    else:
        print("Color code must be RGB formatted, starting with 0x.")
        sys.exit(-1)
else:
    color = "0x00ffff"

idc = r"""
//
// AUTO-GENERATED BY PAIMEI
// http://www.openrce.org
//

#include <idc.idc>

// convenience wrapper around assign_color_to() that will automatically resolve the 'start' and 'end' arguments with
// the start and end address of the block containing ea.
static assign_block_color_to (ea, color)
{
    auto block_start, block_end;

    block_start = find_block_start(ea);
    block_end   = find_block_end(ea);

    if (block_start == BADADDR || block_end == BADADDR)
        return BADADDR;

    assign_color_to(block_start, block_end, color);
}

// the core color assignment routine.
static assign_color_to (start, end, color)
{
    auto ea;

    if (start != end)
    {
        for (ea = start; ea < end; ea = NextNotTail(ea))
            SetColor(ea, CIC_ITEM, color);
    }
    else
    {
        SetColor(start, CIC_ITEM, color);
    }
}

// returns address of start of block if found, BADADDR on error.
static find_block_start (current_ea)
{
    auto ea, prev_ea;
    auto xref_type;

    // walk up from current ea.
    for (ea = current_ea; ea != BADADDR; ea = PrevNotTail(ea))
    {
        prev_ea = PrevNotTail(ea);

        // if prev_ea is the start of the function, we've found the start of the block.
        if (GetFunctionAttr(ea, FUNCATTR_START) == prev_ea)
            return prev_ea;

        // if there is a code reference *from* prev_ea or *to* ea.
        if (Rfirst0(prev_ea) != BADADDR || RfirstB0(ea) != BADADDR)
        {
            xref_type = XrefType();

            // block start found if the code reference was a JMP near or JMP far.
            if (xref_type == fl_JN || xref_type == fl_JF)
                return ea;
        }
    }

    return BADADDR;
}

// returns address of end of block if found, BADADDR on error.
static find_block_end (current_ea)
{
    auto ea, next_ea;
    auto xref_type;

    // walk down from current ea.
    for (ea = current_ea; ea != BADADDR; ea = NextNotTail(ea))
    {
        next_ea = NextNotTail(ea);

        // if next_ea is the start of the function, we've found the end of the block.
        if (GetFunctionAttr(ea, FUNCATTR_END) == next_ea)
            return next_ea;

        // if there is a code reference *from* ea or *to* next_ea.
        if (Rfirst0(ea) != BADADDR || RfirstB0(next_ea) != BADADDR)
        {
            xref_type = XrefType();

            // block end found if the code reference was a JMP near or JMP far.
            if (xref_type == fl_JN || xref_type == fl_JF)
                return next_ea;
        }
    }

    return BADADDR;
}

// return the lower case version of 'str'.
static tolower (str)
{
    auto i, c, newstr;

    newstr = "";

    for (i = 0; i < strlen(str); i++)
    {
        c = substr(str, i, i + 1);

        if (ord(c) >= 0x41 && ord(c) <= 0x5a)
            c = form("%s", ord(c) + 32);

        newstr = newstr + c;
    }

    return newstr;
}

// return the blended color between 'oldcolor' and 'newcolor'.
static blend_color (oldcolor, newcolor)
{
    auto r, g, b, boldcolor, goldcolor, roldcolor, bnewcolor, gnewcolor, rnewcolor;

    boldcolor = (oldcolor & 0xFF0000) >> 16;
    goldcolor = (oldcolor & 0x00FF00) >> 8;
    roldcolor = (oldcolor & 0x0000FF);

    bnewcolor = (newcolor & 0xFF0000) >> 16;
    gnewcolor = (newcolor & 0x00FF00) >> 8;
    rnewcolor = (newcolor & 0x0000FF);

    b    = (boldcolor + (bnewcolor - boldcolor) / 2) & 0xFF;
    g    = (goldcolor + (gnewcolor - goldcolor) / 2) & 0xFF;
    r    = (roldcolor + (rnewcolor - roldcolor) / 2) & 0xFF;

    return (b << 16) + (g << 8) + r;
}

// return the next empty Mark slot
static get_marked_next()
{
    auto slot;
    slot = 1;

    // loop until we find an empty slot
    while(GetMarkedPos(slot) != -1)
        slot++;

    return slot;
}

// executed on script load.
static main()
{
    auto color, this_module, next_mark;

    this_module = GetInputFile();
    next_mark = get_marked_next();

"""
idc += "    if (tolower(this_module) == \"%s\") {\n" % sys.argv[2].lower()
idc += "\n        color = %s;\n" % color


id = None
i=0
f=open(sys.argv[1])
for line in f:
    i+=1
    if id == None:
        if sys.argv[2].lower() in line.lower():
            id, base = line.split(", ")[0:2]
            id = int(id)
            base = int(base, 16)
        else:
            continue

    # We've already found the block id, skip all other process identifiers
    if line[0:7] != "module[":
        continue

    # If this module id matches, grab the base address and add the IDC script
    # line
    try:
        moduleid = int(re.match("module\[\s+(\d+)\]: ", line).groups()[0])
        if moduleid == id:
            blockstart = int(re.match("module\[.*\]: (0x[0-9a-f]+),", line).groups()[0], 16)
            idc += " " * 8 + "if (GetColor(%s, CIC_ITEM) == DEFCOLOR) assign_block_color_to(%s, color);\n" % (hex(base + blockstart), hex(base + blockstart))
    except AttributeError:
        print("%d: %s"%(i,line))
f.close()
idc += r"""
    }
}
"""
f=open(sys.argv[3], "w")
f.write(idc)
f.close()


