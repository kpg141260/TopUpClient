__VERSION__ = "0.5.0.2"
# ruff: noqa: RUF100, UP025, UP004, I001, F401
# -*- coding: utf-8 -*-
try:
    import ujson as json # type: ignore
except:
    import json
import gc


class VersionInfo:
    def __init__(self, ver_fn: str = '/version.json'):
        self.version_dir_file_name: str = ver_fn
        self.ver_dir = {}
        try:
            with open(self.version_dir_file_name, 'r') as f:
                self.ver_dir = json.load(f)
            self.major  = self.ver_dir['project']['build_info']['major']
            self.middle = self.ver_dir['project']['build_info']['middle']
            self.minor  = self.ver_dir['project']['build_info']['minor']
            self.time   = self.ver_dir['project']['build_info']['time']
            self.build  = self.ver_dir['project']['build_info']['time']
        except OSError:
            raise OSError(f'$p${self.version_dir_file_name}$p$ not found')
        except KeyError as ex:
            raise KeyError(f'$p$Key {ex} not found in $p${self.version_dir_file_name}$p$')
        
    def destructor (self):
        self.ver_dir.clear()
        del self.ver_dir
        del self.major
        del self.middle
        del self.time
        del self.build
        del self.version_dir_file_name
        gc.collect()
            
    def __version__(self):
        return f'{self.major}.{self.middle}.{self.minor}.{self.time}.{self.build}'
    
    def __str__(self):
        return f'{self.major}.{self.middle}.{self.minor}.{self.time}.{self.build}'
    
    def __repr__(self):
        return f'{self.major}.{self.middle}.{self.minor}.{self.time}.{self.build}'
    
    def major (self):
        return self.major
    
    def middle (self):
        return self.middle
    
    def minor (self):
        return self.minor
    
    def build_time (self):
        return self.time
    
    def build (self):
        if name not in self.ver_dir:
            if not name.startswith('/'):
                name = f'/{name}'
        return self.build
    
    def short (self, name: str):
        if name not in self.ver_dir:
            if not name.startswith('/'):
                name = f'/{name}'
        return f'{self.major}.{self.ver_dir[name]["build"]}'
    
    def compact (self, name: str):
        if name not in self.ver_dir:
            if not name.startswith('/'):
                name = f'/{name}'
        return f'{self.major}.{self.middle}.{self.ver_dir[name]["build"]}'
    
    def full (self, name: str):
        try:
            if name not in self.ver_dir:
                if not name.startswith('/'):
                    name = f'/{name}'
            return f'{self.major}.{self.middle}.{self.minor}.{self.time}.{self.ver_dir[name]["build"]}'
        except KeyError:
            return 'not found'
    
    def version (self, name: str):
        try:
            return f'{self.major}.{self.middle}.{self.minor}.{self.time}.{self.ver_dir[name]["build"]}'
        except KeyError:
            return f'{name} not found'
