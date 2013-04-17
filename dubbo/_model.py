
class Object(object) :
    '''
        the wapper of java Object
    '''
    def __init__(self, type, fields = None) :
        self._metaType = str(type)
        if fields :
            for (k, v) in fields.items() :
                self.__setattr__(str(k), v)
    
    def __str__(self) :
        temp = self.__dict__.copy()
        del temp['_metaType']
        return self._metaType + ' : ' + str(temp)

class Binary(object) :
    '''
        the wapper of binary data
    '''
    def __init__(self, value) :
        self.value = value
    def __add__(self, value) :
        if self.value == None:
            return Binary(value)
        elif value == None :
            return self
        else:
            return Binary(self.value + value.value)
    def __str__(self) :
        if self.value == None :
            return 'Binary : None'
        else :
            return 'Binary : length =', len(self.value)
