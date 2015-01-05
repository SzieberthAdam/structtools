import struct

STRUCT_FIRSTS = '@=<>!'

def calcsizes(fmt):
  first, body = '', fmt
  if fmt and fmt[0] in STRUCT_FIRSTS:
    first, body = fmt[0], fmt[1:]
  result = []
  remain, exc = body, None
  while remain:
    n, i = 1, 0
    if remain[i] == ' ':
      remain = remain[i+1:]
      continue
    while i < len(remain) - 1 and remain[:i+1].isdecimal():
      i += 1
    if i:
      n = int(remain[:i])
    if not n:
      result.append(0)
    else:
      typechr = remain[i]
      size = struct.calcsize(first + typechr)
      if typechr not in 'xsp':
        result.extend([size]*n)
      else:
        result.append(size*n)
    remain = remain[i+1:]
  return tuple(result)
