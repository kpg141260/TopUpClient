class DbgLevel:
    def __init__(self, name, value, description=None):
        self.name = name
        self.value = value
        self.description = description or name

    def __repr__(self):      return f"<DbgLevel - {self.name}={self.value}>"
    def __str__(self):       return self.name
    def __int__(self):       return self.value
    def __eq__(self, other): return self.value == int(other)
    def __lt__(self, other): return self.value <  int(other)
    def __le__(self, other): return self.value <= int(other)
    def __gt__(self, other): return self.value >  int(other)
    def __ge__(self, other): return self.value >= int(other)
    def __hash__(self):      return hash(self.value)
    def desc (self):         return self.description

class dbg_lvls:
    OFF:        DbgLevel
    DEBUG:      DbgLevel
    INFO:       DbgLevel
    WARNING:    DbgLevel
    ERROR:      DbgLevel
    CRITICAL:   DbgLevel
    TRACE:      DbgLevel
    
    _levels = {
        'OFF':      -1,
        'DEBUG':    10,
        'INFO':     20,
        'WARNING':  30,
        'ERROR':    40,
        'CRITICAL': 50,
        'TRACE':    60,
    }
    
    _name_to_obj = {}
    _value_to_obj = {}

    def __new__ (cls, value):
        """Allow dbg_lvls('DEBUG') style."""
        if isinstance (value, int):
            obj = cls._value_to_obj.get (value)
        else:
            obj = cls._name_to_obj.get (str(value).upper())
        if obj is None:
            raise ValueError(f"Unknown debug level: {value}")
        return obj

    @classmethod
    def get (cls, name):
        """Get level object from name (case-insensitive)."""
        return cls._name_to_obj.get(name.upper(), None)

    @classmethod
    def name (cls, value):
        """Get name from numeric value."""
        obj = cls._value_to_obj.get(value)
        return obj.name if obj else None

    @classmethod
    def setup (cls, desc: dict):
        # Initialise Debug Levels
        # Create named instances like dbg_lvls.DEBUG
        for name, value in dbg_lvls._levels.items ():
            try:
                obj = DbgLevel (name, value, desc.get (name, name))
                setattr (dbg_lvls, name, obj)
                dbg_lvls._name_to_obj[name]  = obj
                dbg_lvls._value_to_obj[value] = obj
            except (ValueError, KeyError):
                raise

desc = {
    "OFF":      "Aus",
    "DEBUG":    "debug",
    "INFO":     "Information",
    "WARNING":  "warning",
    "ERROR":    "error",
    "CRITICAL": "critical",
    "TRACE":    "Fehlersuche"
}
dbg_lvls.setup (desc)

level = dbg_lvls('info')
if level >= dbg_lvls.DEBUG:
    print (repr (level) )
    print (int(level))
    print (level.desc())
    
level = dbg_lvls('info')
print (repr (level) )
print (int(level))
print (level.desc())

print (dbg_lvls.DEBUG)
print (dbg_lvls.INFO)
print (dbg_lvls.ERROR)
print (dbg_lvls.CRITICAL)
print (dbg_lvls.OFF)

print (int(dbg_lvls.ERROR))
print (dbg_lvls.name(60))
print (dbg_lvls(60).desc())

if level >= dbg_lvls.DEBUG:
    print ('Show debug log')
