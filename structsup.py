# TODO: boundary support if native type ("@")

import struct

FIRSTS = '@=<>!'
LENGTHED_TYPECHARS = 'xsp'

def iterinst(fmt):
  if isinstance(fmt, bytes):
    fmt = fmt.decode()
  first, remain = '', fmt
  while remain:
    n, i = 1, 0
    if remain[i] in FIRSTS:
      if i > 0:
        # this will raise an error
        yield struct.Struct(remain[:i+1])
      first = remain[i]
    elif remain[i] != ' ':
      while i < len(remain) - 1 and remain[:i+1].isdecimal():
        i += 1
      if i:
        n = int(remain[:i])
      typechar = remain[i]
      if not n or (n and typechar in LENGTHED_TYPECHARS):
        yield struct.Struct(first + str(n) + typechar)
      else:
        s = struct.Struct(first + typechar)
        for _ in range(n):
          yield s
    remain = remain[i+1:]

def insts(fmt):
  return tuple(iterinst(fmt))

def itersizes(fmt):
  yield from (s.size for s in iterinst(fmt))

def sizes(fmt):
  return tuple(itersizes(fmt))
