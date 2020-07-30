from XoneK2 import XoneK2
import DebugPrint

def create_instance(c_instance):
    DebugPrint.set_c_instance(c_instance)
    return XoneK2(c_instance)
