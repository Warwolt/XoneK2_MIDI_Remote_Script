_c_instance = None

def set_c_instance(c_instance):
    ''' Store a ref to the controller instance '''
    c_instance.log_message("set_c_instance called")
    global _c_instance
    _c_instance = c_instance

def log_message(*args, **kwargs):
    ''' Print a debug message via the stored controller instance '''
    _c_instance.log_message(*args, **kwargs)

# https://stackoverflow.com/a/192184
def dump_object(obj):
    ''' Dump all attributes in obj and return as newline separated strings. '''
    s = ""
    for attr in dir(obj):
        s = s + "\nobj.%s = %r" % (attr, getattr(obj, attr))
    return
