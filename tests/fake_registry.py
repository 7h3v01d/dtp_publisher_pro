# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""A stand-in for HKEY_CURRENT_USER.  conftest.py gives every test a fresh
one, so no test ever reads or writes the real Windows registry."""


class FakeRegistry:
    """Case-insensitive keys, like the real registry; creating a key creates
    its parents."""

    def __init__(self):
        self.keys = {}                      # lower-case path -> {name: value}

    @staticmethod
    def _k(key):
        return key.lower().strip("\\")

    def get(self, key, name=""):
        return self.keys.get(self._k(key), {}).get(name)

    def has_key(self, key):
        return self._k(key) in self.keys

    def set(self, key, name, value):
        k = self._k(key)
        parts = k.split("\\")
        for i in range(1, len(parts) + 1):
            self.keys.setdefault("\\".join(parts[:i]), {})
        self.keys[k][name] = value

    def delete_value(self, key, name):
        self.keys.get(self._k(key), {}).pop(name, None)

    def delete_tree(self, key):
        k = self._k(key)
        for p in [p for p in self.keys if p == k or p.startswith(k + "\\")]:
            del self.keys[p]

    def is_empty(self, key):
        k = self._k(key)
        if k not in self.keys:
            return False
        return not self.keys[k] and not any(p.startswith(k + "\\") for p in self.keys)

    def snapshot(self):
        return {k: dict(v) for k, v in self.keys.items() if v}


class FakeWinreg:
    """Just enough of the ``winreg`` module, with its strictness: missing keys
    raise FileNotFoundError and DeleteKey refuses a key that has subkeys."""

    HKEY_CURRENT_USER = "HKCU"
    KEY_WRITE = KEY_ALL_ACCESS = KEY_READ = 0
    REG_SZ = 1

    def __init__(self):
        self.reg = FakeRegistry()

    class _Handle:
        def __init__(self, path):
            self.path = path

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def Close(self):
            pass

    def OpenKey(self, root, key, reserved=0, access=0):
        if not self.reg.has_key(key):
            raise FileNotFoundError(2, "The system cannot find the file specified", key)
        return self._Handle(FakeRegistry._k(key))

    def CreateKeyEx(self, root, key, reserved=0, access=0):
        k = FakeRegistry._k(key)
        parts = k.split("\\")
        for i in range(1, len(parts) + 1):
            self.reg.keys.setdefault("\\".join(parts[:i]), {})
        return self._Handle(k)

    def QueryValueEx(self, h, name):
        vals = self.reg.keys[h.path]
        if name not in vals:
            raise FileNotFoundError(2, "value not found", name)
        return vals[name], self.REG_SZ

    def SetValueEx(self, h, name, reserved, kind, value):
        assert isinstance(value, str) and kind == self.REG_SZ
        self.reg.keys[h.path][name] = value

    def DeleteValue(self, h, name):
        if name not in self.reg.keys[h.path]:
            raise FileNotFoundError(2, "value not found", name)
        del self.reg.keys[h.path][name]

    def _children(self, path):
        return sorted({p[len(path) + 1:].split("\\")[0] for p in self.reg.keys
                       if p.startswith(path + "\\")})

    def EnumKey(self, h, i):
        kids = self._children(h.path)
        if i >= len(kids):
            raise OSError(259, "No more data is available")
        return kids[i]

    def DeleteKey(self, root, key):
        k = FakeRegistry._k(key)
        if k not in self.reg.keys:
            raise FileNotFoundError(2, "not found", key)
        if self._children(k):
            raise PermissionError(5, "Access is denied (key has subkeys)", key)
        del self.reg.keys[k]

    def QueryInfoKey(self, h):
        return len(self._children(h.path)), len(self.reg.keys[h.path]), 0
