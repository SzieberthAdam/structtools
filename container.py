import collections
import itertools
import struct

from . import structsup


Result = collections.namedtuple('Result',
                                'value data datasize subsize')


class ContainerException(Exception):
  pass


class BaseClassMethodError(ContainerException,
                           NotImplementedError):
  def __init__(self):
    errmsg = 'method should get implemented by child class'
    super().__init__(errmsg)


class InitializationPosArgMissingError(ContainerException):
  def __init__(self, min_num=1):
    errmsg = 'positional argument missing (minimum {} expected)'
    super().__init__(errmsg.format(min_num))


class InitializationTypeError(ContainerException, TypeError):
  def __init__(self, name, value, valid_type):
    errmsg = 'invalid {} param type: {} (expected {})'
    super().__init__(errmsg.format(name, value, valid_type))


class InitializationValueError(ContainerException, ValueError):
  def __init__(self, name, value, valids=None):
    errmsg = 'invalid {} param value: {}'.format(name, value)
    if valids is not None:
      valids_repr = [v.__repr__() for v in sorted(valids)]
      errmsg += ' (valids: {})'.format(', '.join(valids_repr))
    super().__init__(errmsg)


class InvalidParamSizeError(ContainerException):
  def __init__(self, paramname, expsize, cond=''):
    errmsg = 'param {} is invalid, expected {} size: {}'
    super().__init__(errmsg.format(paramname, cond, expsize))


class InvalidStructFormatError(ContainerException, ValueError):
  def __init__(self, fmt):
    super().__init__('invalid struct format: {!r}'.format(fmt))


class NotFixedSizeError(ContainerException):
  def __init__(self):
    super().__init__('size is not fixed')


class NotStoppedError(ContainerException):
  def __init__(self, stop):
    errmsg = 'should end with stop string: {!r}'.format(stop)
    super().__init__(errmsg)


class Container:

  @classmethod
  def validate(cls, obj):
    if not isinstance(obj, cls):
      errmsg = 'invalid c: {!r}'
      raise ContainerException(errmsg.format(obj))

  @property
  def fixed(self):
    return (self.datasize is not None)

  @property
  def datasize(self):
    if hasattr(self, '_datasize'):
      return self._datasize

  def subc(self, datasize):
    if self.fixed and datasize != self.datasize:
      errargs = 'datasize', datasize, self.datasize
      raise InvalidParamSizeError(*errargs)

  def trim_data(self, data, is_entire):
    if self.fixed:
      if is_entire and len(data) != self.datasize:
        raise InvalidParamSizeError('data', self.datasize)
      elif not is_entire:
        return data[:self.datasize]
    return data

  def data(self, v):
    raise NotImplementedMethodError()

  def value(self, data, is_entire=False):
    raise NotImplementedMethodError()


class NestedContainer(Container):

  @property
  def seqtype(self):
    if self.fixed:
      return tuple
    return list


class FixedSizeStructBasedContainer(Container):

  DEFAULT_FMT_FIRST = '<'
  _valid_fmt_first = '<>='

  def __init__(self, fmt, fmt_first=None):
    super().__init__()
    self._fixed = True
    self._fmt = fmt
    if fmt_first is None:
      fmt_first = self.DEFAULT_FMT_FIRST
    if fmt_first not in self._valid_fmt_first:
      errargs = 'fmt_first', fmt_first, self._valid_fmt_first
    self._fmt_first = fmt_first
    self._subsize = structsup.sizes(self.fmt)
    self._datasize = sum(self._subsize)

  @property
  def fmt(self):
    return self._fmt_first + self._fmt

  @property
  def subsize(self):
    return self._subsize

  def data(self, value):
    ds, ss = self.datasize, self.subsize
    return Result(value, struct.pack(self.fmt, *value), ds, ss)

  def value(self, data, is_entire=False):
    ds, ss = self.datasize, self.subsize
    data = self.trim_data(data, is_entire)
    return Result(struct.unpack(self.fmt, data), data, ds, ss)


class Integer(FixedSizeStructBasedContainer):

  _valid_sizes = {1: 'Bb',2: 'Hh', 4: 'Ii', 8: 'Qq'}

  def __init__(self, size=4, signed=False, **kwargs):
    if size not in self._valid_sizes:
      errargs = 'size', size, self._valid_sizes
      raise InitializationValueError(*errargs)
    fmt = self._valid_sizes[size][int(bool(signed))]
    super().__init__(fmt, **kwargs)
    self._subsize = self._subsize[0]

  def _norm_result(self, r):
    ds, ss = self.datasize, self.subsize
    return Result(r.value[0], r.data, ds, ss)

  def data(self, value):
    return self._norm_result(super().data((value,)))

  def value(self, data, **kwargs):
    return self._norm_result(super().value(data, **kwargs))


class String(Container):
  def __init__(self, encoding='utf-8'):
    super().__init__()
    self._encoding = encoding

  @property
  def encoding(self):
    return self._encoding


class VarSizeString(String):

  def __init__(self, sizec=None, **kwargs):
    super().__init__(**kwargs)
    self._fixed = False
    if sizec is None:
      self._sizec = Integer()
    else:
      Integer.validate(sizec)
      self._sizec = sizec

  @property
  def sizec(self):
    return self._sizec

  @property
  def subc(self):
    return self

  def data(self, value):
    str_data = value.encode(self.encoding)
    sizec_result = self.sizec.data(len(str_data))
    data = sizec_result.data + str_data
    subsize = sizec_result.datasize, len(str_data)
    datasize = sum(subsize)
    return Result(value, data, datasize, subsize)

  def value(self, data, is_entire=False):
    sizec_result = self.sizec.value(data)
    subsize = sizec_result.datasize, sizec_result.value
    datasize = sum(subsize)
    if is_entire and len(data) != datasize:
      raise InvalidParamSizeError('data', datasize)
    elif not is_entire:
      data = data[:datasize]
    value = data[subsize[0]:].decode(self.encoding)
    return Result(value, data, datasize, subsize)


class StoppedString(String):

  def __init__(self, stop=b'\x00', **kwargs):
    super().__init__(**kwargs)
    self._fixed = False
    if not isinstance(stop, bytes):
      raise InitializationTypeError('stop', stop, 'bytes')
    self._stop = stop

  @property
  def stop(self):
    return self._stop

  def data(self, value):
    data = value.encode(self.encoding) + self.stop
    datasize = len(data)
    subsize = datasize - len(self.stop), len(self.stop)
    return Result(value, data, datasize, subsize)

  def value(self, data, is_entire=False):
    if is_entire and not data.endswith(self.stop):
      raise NotStoppedError(self.stop)
    elif not is_entire:
      buf = b''
      for l in range(len(data)+1):
        buf = data[:l]
        if buf.endswith(self.stop):
          break
      else:
        raise NotStoppedError(self.stop)
      data = buf
    datasize = len(data)
    subsize = datasize - len(self.stop), len(self.stop)
    value = data[:subsize[0]].decode(self.encoding)
    return Result(value, data, datasize, subsize)


class Array(NestedContainer):
  def __init__(self, elementc, n=None, **kwargs):
    super().__init__(**kwargs)
    Container.validate(elementc)
    self._elementc = elementc
    if n is not None:
      if not isinstance(n, int):
        raise InitializationTypeError('n', n, 'int')
      if n < 1:
        raise InitializationValueError('n', n)
    self._n = n
    if n is not None and elementc.fixed:
      self._datasize = self.n * elementc.size

  @property
  def elementc(self):
    return self._elementc

  @property
  def n(self):
    return self._n

  def data(self, value):
    if self.n is not None and len(value) != self.n:
      raise InvalidParamSizeError('value', self.n)
    eresults = [self.elementc.data(v)
                       for i, v in enumerate(value)]
    data = b''.join([r.data for r in eresults])
    datasize = len(data)
    subsize = self.seqtype(r.subsize for r in eresults)
    if not isinstance(value, self.seqtype):
      value = self.seqtype(value)
    return Result(value, data, datasize, subsize)

  def value(self, data, is_entire=False):
    data = self.trim_data(data, is_entire)
    if self.elementc.fixed:
      edatasize = self.elementc.datasize
      if len(data) % edatasize:
        errexpsize = 'multiple of {}'.format(edatasize)
        raise InvalidParamSizeError('data', errexpsize)
      # foreign code used:
      # http://code.activestate.com/recipes/303060/
      chunkit = zip(*[itertools.islice(data, i, None, edatasize)
                    for i in range(edatasize)])
      it = (self.elementc.value(bytes(t), is_entire=True)
            for t in chunkit)
    else:
      it = self._iter_varsize_eresults(data)
    eresults = list(it)
    value = self.seqtype(r.value for r in eresults)
    datasize = sum(r.datasize for r in eresults)
    subsize = self.seqtype(r.subsize for r in eresults)
    return Result(value, data, datasize, subsize)

  def _iter_varsize_eresults(self, data):
    n, i = 0, 0
    while data[i:]:
      if self.n is not None and n == self.n:
        break
      result = self.elementc.value(data[i:])
      yield result
      i += result.datasize
      n += 1


class VarSizeArray(NestedContainer):

  def __init__(self, elementc, sizec=None, **kwargs):
    super().__init__(**kwargs)
    Container.validate(elementc)
    self._elementc = elementc
    if sizec is None:
      self._sizec = Integer()
    else:
      Integer.validate(sizec)
      self._sizec = sizec

  @property
  def elementc(self):
    return self._elementc

  @property
  def sizec(self):
    return self._sizec

  def data(self, value):
    sizec_result = self.sizec.data(len(value))
    eresults = [self.elementc.data(v)
                       for i, v in enumerate(value)]
    element_data = b''.join([r.data for r in eresults])
    data = sizec_result.data + element_data
    datasize = len(data)
    element_subsize = self.seqtype(r.subsize for r in eresults)
    subsize = sizec_result.datasize, element_subsize
    if not isinstance(value, self.seqtype):
      value = self.seqtype(value)
    return Result(value, data, datasize, subsize)

  def value(self, data, is_entire=False):
    sizec_result = self.sizec.value(data)
    n = sizec_result.value
    edata = data[sizec_result.datasize:]
    if self.elementc.fixed:
      edatasize = self.elementc.datasize
      esize = n * edatasize
      datasize = sizec_result.datasize + esize
      if is_entire and datasize != len(data):
        raise InvalidParamSizeError('data', datasize)
      elif not is_entire:
        if len(data) < datasize:
          errargs = 'data', datasize, 'minimum'
          raise InvalidParamSizeError(*errargs)
        data = data[:datasize]
        edata = data[sizec_result.datasize:]
      # foreign code used:
      # http://code.activestate.com/recipes/303060/
      chunkit = zip(*[itertools.islice(edata, i, None,
                    edatasize) for i in range(edatasize)])
      it = (self.elementc.value(bytes(t), is_entire=True)
            for t in chunkit)
    else:
      it = self._iter_varsize_eresults(edata, n, is_entire)
    eresults = list(it)
    value = self.seqtype(r.value for r in eresults)
    datasize = len(data)
    esubsize = self.seqtype(r.subsize for r in eresults)
    subsize = sizec_result.datasize, esubsize
    return Result(value, data, datasize, subsize)

  def _iter_varsize_eresults(self, edata, n, is_entire):
      i = 0
      for _ in range(n):
        result = self.elementc.value(edata[i:])
        yield result
        i += result.datasize
      if is_entire and edata[i:]:
        raise InvalidParamSizeError('data', 'various')


class Row(NestedContainer):
  def __init__(self, *elementcs, n=None, **kwargs):
    super().__init__(**kwargs)
    if not elementcs:
      raise InitializationPosArgMissingError()
    [Container.validate(c) for c in elementcs]
    self._elementcs = elementcs
    if n is not None:
      if n != len(elementcs):
        errargs = 'n', n, (len(elementcs),)
        raise InitializationValueError(*errargs)
    self._n = n
    if all(c.fixed for c in elementcs):
      self._datasize = sum(c.datasize for c in elementcs)

  @property
  def elementcs(self):
    return self._elementcs

  @property
  def fixed(self):
    return self._n is not None and super().fixed

  @property
  def n(self):
    if self._n is not None:
      return self._n
    return len(self.elementcs)

  def data(self, value):
    if len(value) != self.n:
      raise InvalidParamSizeError('value', self.n)
    eresults = [self.elementcs[i].data(v)
                       for i, v in enumerate(value)]
    data = b''.join([r.data for r in eresults])
    datasize = len(data)
    subsize = self.seqtype(r.subsize for r in eresults)
    return Result(value, data, datasize, subsize)

  def value(self, data, is_entire=False):
    data = self.trim_data(data, is_entire)
    eresults = list(self._iter_eresults(data, is_entire))
    datasize = sum(r.datasize for r in eresults)
    if is_entire and datasize != len(data):
      raise InvalidParamSizeError('data', datasize)
    value = self.seqtype(r.value for r in eresults)
    subsize = self.seqtype(r.subsize for r in eresults)
    return Result(value, data, datasize, subsize)

  def _iter_eresults(self, data, is_entire):
      i = 0
      for e in range(self.n):
        result = self.elementcs[e].value(data[i:])
        yield result
        i += result.datasize
      if is_entire and data[i:]:
        raise InvalidParamSizeError('data', 'various')


class StandardDictionary(Array):

  def __init__(self, keyc, valuec, **kwargs):
    [Container.validate(c) for c in (keyc, valuec)]
    self._keyc = keyc
    self._valuec = valuec
    elementc = Row(keyc, valuec)
    super().__init__(elementc, **kwargs)

  @property
  def keyc(self):
    return self._keyc

  @property
  def valuec(self):
    return self._valuec

  def data(self, value):
    super_value = tuple((k, v) for k, v in value.items())
    r = super().data(super_value)
    if not isinstance(value, collections.OrderedDict):
      value = collections.OrderedDict(super_value)
    return Result(value, r.data, r.datasize, r.subsize)

  def value(self, data, is_entire=False):
    r = super().value(data)
    return Result(collections.OrderedDict(r.value), r.data,
                  r.datasize, r.subsize)
