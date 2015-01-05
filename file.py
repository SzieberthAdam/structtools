# IN TEMPORARY STATE

import functools
import os

from . import container


class DataFileException(Exception):
  pass


class DataFile:

  @staticmethod
  def iomethod(f):
    @functools.wraps(f)
    def wrapper(self, *args, **kwargs):
      if self._opened:
        return f(self, *args, **kwargs)
      with self:
        return f(self, *args, **kwargs)
    return wrapper

  def __init__(self, filename, c, buffered=False):
    # initializes private properties of the file object and for
    # the state which tracks the instance to be opened or not
    self._f, self._opened = None, False
    self._filename = filename
    container.Container.validate(c)
    self.c = c
    self._buffered = bool(buffered)
    self._subsize = None

  def __enter__(self):
    """
    Enters the context. Opens and returns itself.
    """
    self.open()
    return self

  def __exit__(self, exc_type, exc_value, exc_traceback):
    """
    Exits the context. Closes itself.
    """
    self.close()

  @property
  def buffered(self):
    return self._buffered

  @property
  def c(self):
    return self.c

  @property
  def filename(self):
    return self._filename

  def open(self):
    """
    Opens itself. It creates the file if not exists.
    """
    if self._opened:
      raise DataFileException('already opened')
    mode = 'r+b'
    if not os.path.exists(self.filename):
      mode = 'w+b'
    self._f = open(self.filename, mode)
    self._opened = True

  def close(self):
    """
    Closes itself.
    """
    if not self._opened:
      raise FileFormatException('not opened yet')
    self._f.close()
    self._opened = False




class DictionaryDataFile(DataFile):

  def __init__(self, filename, keyc, valc,
               **kwargs):
    super().__init__(filename, **kwargs)
    cs_ = keyc, valc
    # validates containers
    [container.ValueType.validate(vt) for vt in cs_]
    self.cs = cs_
    self._keyi, self._pos = {}, []
    if self.buffered:
      self._values = []
    self.reload()

  @property
  def keyc(self):
    return self.cs[0]

  @property
  def valc(self):
    return self.cs[1]

  def __getitem__(self, key):
    if self.buffered:
      return self._values[self._keyi[key]]
    return self._getitem_from_data(key)

  def keys(self):
    return self._keyi.keys()

  @DataFile.iomethod
  def _getitem_from_data(self, key):
    pos = self._pos[self._keyi[key]]
    s = slice(sum(pos[:2]), sum(pos))
    self._f.seek(sum(pos[:2]))
    data = self._f.read(pos[2])
    return self.valc.sizeval(data, is_entire=True)[1]

  @DataFile.iomethod
  def __setitem__(self, key, val):
    key_size, key_data = self.keyc.sizedata(key)
    val_size, val_data = self.valc.sizedata(val)
    if key not in self.keys():
      self._f.seek(0, 2)  # this one seeks to EOF
      self._f.write(key_data + val_data)
      self._pos.append([self.file_size(), key_size, val_size])
      self._keyi[key] = len(self._keyi)
    else:
      keyi = self._keyi[key]
      curr_pos = self._pos[keyi]
      new_pos = [curr_pos[0], key_size, val_size]
      delta = sum(new_pos) - sum(curr_pos)
      trail_data = b''
      if delta:
        self._f.seek(sum(curr_pos))
        trail_data = self._f.read()
        self._f.truncate(curr_pos[0])
      self._f.seek(curr_pos[0])
      self._f.write(key_data + val_data + trail_data)
      self._pos[keyi] = new_pos
      if len(self._pos) > keyi + 1:
        for p in self._pos[keyi+1:]:
          p[0] += delta

  @DataFile.iomethod
  def __delitem__(self, key):
      keyi = self._keyi[key]
      pos = self._pos[keyi]
      data_size = sum(pos[1:])
      self._f.seek(sum(pos))
      trail_data = self._f.read()
      self._f.seek(pos[0])
      self._f.truncate()
      self._f.write(trail_data)
      new_pos = self._pos[:keyi]
      new_pos.extend([[p[0]-data_size] + p[1:]
                      for p in self._pos[keyi+1:]])
      self._pos = new_pos
      del self._keyi[key]
      self._keyi = {k: (i if i < keyi else i-1)
                    for k, i in self._keyi.items()}

  def file_size(self):
    if not self._pos:
      return 0
    return sum(self._pos[-1])

  @DataFile.iomethod
  def reload(self):
    self._f.seek(0)
    data = self._f.read()
    i, key_state = 0, True
    while data[i:]:
      if key_state:
        key_data = data[i:]
        key_size, key = self.keyc.sizeval(key_data)
        if key in self.keys():
          raise DataFileException('key is already present')
      else:
        val_data = data[i+key_size:]
        val_size, val = self.valc.sizeval(val_data)
        if self.buffered:
          self._values.append(value)
        self._keyi[key] = len(self._keyi)
        self._pos.append([i, key_size, val_size])
        i += key_size + val_size
      key_state = (not key_state)

