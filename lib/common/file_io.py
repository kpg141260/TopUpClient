__VERSION__ = "0.6.0.4"
# ruff: noqa: RUF100, UP025, UP004, I001, F401, S110, E722, BLE001
# -*- coding: utf-8 -*-
try:
    import ujson as json # type: ignore
except:
    import json

class FILE_IO:
    def __init__ (self, 
                  use_encryption: bool = False, 
                  seed_file: str = '', 
                  shift: int = 5):
        self.txt_dne  = '{} File $p${}$p$ does not exist!'
        self.txt_ioe  = '{} File $p${}$p$ I/O Error!'
        self.txt_pde  = '{} File $p${}$p$ permission denied!'
        self.txt_rde  = '{} File $p${}$p$ Read Error!'
        self.txt_wte  = '{} File $p${}$p$ Write Error!'
        self.txt_type = '{} File $p${}$p$ Type Error - data must be dict or str'
        
        if use_encryption:
            if seed_file == '':
                self._crypto = None
                raise RuntimeError ('No file name for encryption key provided. Encryption disabled.')    
            try:
                from cipher import AESCipher
                self._crypto = AESCipher (seed_file=seed_file, shift=shift)
            except:
                self._crypto = None
        
    def destructor (self):
        del self.txt_dne
        del self.txt_ioe
        del self.txt_pde
        del self.txt_rde
        del self.txt_wte
        
        del self.txt_type
        try:
            self._crypto.destructor()
            del self._crypto
        except:
            pass
    
    def load_json (self, fn: str):
        return self._load_file (fn, file_type='json')
    
    def load_file (self, fn: str) -> str:
        return self._load_file (fn, file_type='')
    
    def load_decrypt (self, fn: str):
        data = self._load_file (fn)
        if self._crypto:
            data = self._crypto.decrypt (data)
        return data
    
    def _load_file (self, fn: str, file_type: str = ''):
        try:
            if file_type == 'json':
                with open (fn, 'r') as f:
                    return json.load (f)
            else:
                with open (fn, 'r') as f:
                    return f.read()
        except OSError as ex:
            if ex.args[0] == 2:
                raise OSError (self.txt_dne.format (__name__, fn))
            elif ex.args[0] == 6:
                raise OSError (self.txt_ioe.format (__name__, fn))
            elif ex.args[0] == 13:
                raise OSError (self.txt_pde.format (__name__, fn))
            raise
        except Exception:
            raise OSError (self.txt_rde.format (__name__, fn))
    
    def write (self, fn: str, data: str):
        self._write_file (fn, data)

    def write_encrypt (self, in_fn: str, out_fn: str = ''):
        if self._crypto:
            with open (in_fn, 'r') as f:
                data = f.read()
            data = self._crypto.encrypt (data)
        if out_fn == '':
            out_fn = in_fn
        self._write_file (out_fn, data)

    def _write_file (self, fn: str, data, mode: str = 'w'):
        try:
            if isinstance (data, dict):
                with open (fn, mode) as f:
                    json.dump (data, f)
            elif isinstance (data, str):
                with open (fn, mode) as f:
                    f.write (data)
            else:
                raise TypeError (f'{__class__} data must be a dictionary or string')

        except OSError as ex:
            if ex.args[0] == 2:
                raise OSError (self.txt_dne.format (__name__, fn))
            elif ex.args[0] == 6:
                raise OSError (self.txt_ioe.format (__name__, fn))
            elif ex.args[0] == 13:
                raise OSError (self.txt_pde.format (__name__, fn))
            raise

        except TypeError as ex:
            raise TypeError (self.txt_type.format (__name__, fn))

        except Exception as ex:
            raise OSError (self.txt_wte.format (__name__, fn))
