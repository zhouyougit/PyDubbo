#!/usr/bin/python
#coding:utf-8

import types
import datetime
import time
import struct
import pdb
from cStringIO import StringIO

_Hessian2Input__debug = False

class Binary(object) :
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

class ClassDef(object) :
    def __init__(self, type, fieldNames) :
        self.type = type
        self.fieldNames = fieldNames
    def __str__(self) :
        return 'ClassDef : ' + self.type + ' [' + ','.join(self.fieldNames) + ']'

class Object(object) :
    def __init__(self, type, fields = None) :
        self._metaType = str(type)
        if fields :
            for (k, v) in fields.items() :
                self.__setattr__(str(k), v)
    
    def __str__(self) :
        temp = self.__dict__.copy()
        del temp['_metaType']
        return self._metaType + ' : ' + str(temp)

ENCODERS = {}

def encoderFor(data_type):
    def register(f):
        # register function `f` to encode type `data_type`
        ENCODERS[data_type] = f
        return f
    return register


def printByteStr(encodeStr) :
    outstr = ''
    col = 0
    for c in encodeStr :
        outstr += '%02x ' % (ord(c))
        col += 1
        if col >= 16 :
            col = 0
            outstr += '\n'
    print outstr

class Hessian2Output(object) :
    def __init__(self) :
        self.output = StringIO()
        self.types = []
        self.classDefs = []
        self.refs = []
    
    def getByteString(self) :
        return self.output.getvalue()

    def writeObject(self, value) :
        self.__mWriteObject(value)

    def getLength(self) :
        return len(self.output.getvalue())

    def __write(self, value) :
        self.output.write(value)

    def __writeByte(self, value) :
        self.__write(chr(value))

    def __pack(self, formatStr, value) :
        self.__write(struct.pack(formatStr, value))

    def __mWriteObject(self, obj) :
        if type(obj) in ENCODERS :
            encoder = ENCODERS[type(obj)]
            encoder(self, obj)
        else :
            raise TypeError('encoder cannot serialize %s' % (type(obj),))

    @encoderFor(types.NoneType)
    def __encodeNull(self, value) :
        self.__write('N')

    @encoderFor(types.BooleanType)
    def __encodeBoolean(self, value) :
        if value :
            self.__write('T')
        else :
            self.__write('F')

    @encoderFor(types.IntType)
    def __encodeInt(self, value) :
        '''
        int ::= 'I' b3 b2 b1 b0
            ::= [x80-xbf]       
            -16 <= value <= 47  value = code - 0x90
            ::= [xc0-xcf] b0    
            -2048 <= value <= 2047  value = ((code - 0xc8) << 8) + b0
            ::= [xd0-xd7] b1 b0
            -262144 <= value <= 262143  value = ((code - 0xd4) << 16) + (b1 << 8) + b0
        '''
        if -16 <= value <= 47 :
            self.__writeByte(0x90 + value)
        elif -2048 <= value <= 2047 :
            self.__writeByte(0xc8 + (value >> 8))
            self.__writeByte(value & 0xff)
        elif -262144 <= value <= 262143 :
            self.__writeByte(0xd4 + (value >> 16))
            self.__pack('>H', (value >> 8))
        else :
            self.__write('I')
            self.__pack('>i', value)

    @encoderFor(types.LongType)
    def __encodeLong(self, value) :
        '''
         long ::= L b7 b6 b5 b4 b3 b2 b1 b0
              ::= [xd8-xef]
                -8 <= value <= 15  value = (code - 0xe0)
              ::= [xf0-xff] b0
                -2048 <= value <= 2047  value = ((code - 0xf8) << 8) + b0
              ::= [x38-x3f] b1 b0
                -262144 <= value <= 262143  value = ((code - 0x3c) << 16) + (b1 << 8) + b0
              ::= x59 b3 b2 b1 b0
                -0x80000000L <= value <= 0x7fffffffL value = (b3 << 24) + (b2 << 16) + (b1 << 8) + b0
        '''
        if -8 <= value and value <= 15 :
            self.__writeByte(0xe0 + value)
        elif -2048 <= value <= 2047 :
            self.__writeByte(0xf8 + (value >> 8))
            self.__writeByte(value & 0xff)
        elif -262144 <= value <= 262143 :
            self.__writeByte(0x3c + (value >> 16))
            self.__pack('>H', (value >> 8))
        elif -0x80000000L <= value <= 0x7fffffffL:
            self.__write('\x59')
            self.__pack('>i', value)
        else :
            self.__write('L')
            self.__pack('>q', value)

    @encoderFor(types.FloatType)
    def __encodeFloat(self, value) :
        '''
        double ::= D b7 b6 b5 b4 b3 b2 b1 b0
               ::= x5b      value = 0.0
               ::= x5c      value = 1.0
               ::= x5d b0   
                -128.0 <= value <= 127.0    value = (double) b0
               ::= x5e b1 b0
                -32768.0 <= value <= 32767.0, value = (double)(256 * b1 + b0)
               ::= x5f b3 b2 b1 b0
                32bit float
        '''
        intValue = int(value)
        if intValue == value :
            if intValue == 0 :
                self.__write('\x5b')
            elif intValue == 1 :
                self.__write('\x5c')
            elif -128 <= intValue <= 127 :
                self.__write('\x5d')
                self.__writeByte(value & 0xff)
            elif -32768 <= value <= 32767 :
                self.__write('\x5e')
                self.__pack('>h', value)
            return
        mills = int(value * 1000);
        if (0.001 * mills) == value :
            self.__write('\x5f')
            self.__pack('>f', value)
        else :
            self.__write('D')
            self.__pack('>d', value)
            

    @encoderFor(datetime.datetime)
    def __encodeDate(self, value) :
        '''
            date ::= x4a b7 b6 b5 b4 b3 b2 b1 b0
                a 64-bit long of milliseconds since Jan 1 1970 00:00H, UTC.
                 ::= x4b b4 b3 b2 b1 b0
                a 32-bit int of minutes since Jan 1 1970 00:00H, UTC.
        '''
        if value.second == 0 and value.microsecond / 1000 == 0 :
            self.__write('\x4b')
            minutes = int(time.mktime(value.timetuple())) / 60
            self.__pack('>i', minutes)
        else :
            self.__write('\x4a')
            milliseconds = int(time.mktime(value.timetuple())) * 1000 
            milliseconds += value.microsecond / 1000
            self.__pack('>q', milliseconds)

    @encoderFor(time.struct_time)
    def __encodeDate2(self, value) :
        '''
            date ::= x4a b7 b6 b5 b4 b3 b2 b1 b0
                a 64-bit long of milliseconds since Jan 1 1970 00:00H, UTC.
                 ::= x4b b4 b3 b2 b1 b0
                a 32-bit int of minutes since Jan 1 1970 00:00H, UTC.
        '''
        if value.second == 0 and value.microsecond / 1000 == 0 :
            self.__write('\x4b')
            minutes = int(time.mktime(value)) / 60
            self.__pack('>i', minutes)
        else :
            self.__write('\x4a')
            milliseconds = int(time.mktime(value)) * 1000 
            milliseconds += value.microsecond / 1000
            self.__pack('>q', milliseconds)

    @encoderFor(types.StringType)
    def __encodeString(self, value) :
        '''
        string ::= x52 b1 b0 <utf8-data> string
               ::= S b1 b0 <utf8-data>
               ::= [x00-x1f] <utf8-data>
               ::= [x30-x33] b0 <utf8-data>
        '''
        try :
            value = value.encode('ascii')
        except UnicodeDecodeError:
            raise TypeError('string containing bytes out of range 0x00-0x79, use Binary or unicode objects instead')
        length = len(value)
        
        while length > 65535 :
            self.__write('\x52')
            self.__pack('>H', 65535)
            self.__write(value[:65535])
            value = value[65535:]
            length -= 65535
        
        if length <= 31 :
            self.__writeByte(length)
        elif length <= 1023 :
            self.__writeByte(0x30 + (length >> 8))
            self.__writeByte(length & 0xff)
        else :
            self.__write('S')
            self.__pack('>H', length)
        
        if length > 0 :
            self.__write(value)

    @encoderFor(types.UnicodeType)
    def __encodeUnicode(self, value) :
        '''
        string ::= x52 b1 b0 <utf8-data> string
               ::= S b1 b0 <utf8-data>
               ::= [x00-x1f] <utf8-data>
               ::= [x30-x33] b0 <utf8-data>
        '''
        length = len(value)
        
        while length > 65535 :
            self.__write('\x52')
            self.__pack('>H', 65535)
            self.__write(value[:65535].encode('utf-8'))
            value = value[65535:]
            length -= 65535
        
        if length <= 31 :
            self.__writeByte(length)
        elif length <= 1023 :
            self.__writeByte(0x30 + (length >> 8))
            self.__writeByte(length & 0xff)
        else :
            self.__write('S')
            self.__pack('>H', length)
        
        if length > 0 :
            self.__write(value.encode('utf-8'))

    def __addRef(self, value) :
        refId = 0
        for ref in self.refs :
            if value is ref :
                self.__write('\x51')
                self.__encodeInt(refId)
                return True
            refId += 1

        self.refs.append(value)
        return False

    @encoderFor(types.ListType)
    def __encodeList(self, value) :
        ''' list ::= x57 value* 'Z'        # variable-length untyped list '''
        if self.__addRef(value) :
            return

        self.__write('\x57')
        for element in value :
            self.__mWriteObject(element)
        self.__write('Z')

    @encoderFor(types.TupleType)
    def __encodeTuple(self, value) :
        '''
            ::= x58 int value*        # fixed-length untyped list
            ::= [x78-7f] value*       # fixed-length untyped list
        '''
        if self.__addRef(value) :
            return

        if len(value) <= 7 :
            self.__writeByte(0x78 + len(value))
        else :
            self.__write('\x58')
            __encodeInt(len(value))
        for element in value :
            self.__mWriteObject(element)

    @encoderFor(types.DictType)
    def __encodeDict(self, value) :
        '''
            map ::= 'M' type (value value)* 'Z'
                ::= 'H' (value value)* 'Z'
        '''
        if self.__addRef(value) :
            return

        self.__write('H')
        for (k, v) in value.items() :
            self.__mWriteObject(k)
            self.__mWriteObject(v)
        self.__write('Z')

    @encoderFor(Binary)
    def __encodeBinary(self, value) :
        '''
            binary ::= x41 b1 b0 <binary-data> binary
                   ::= B b1 b0 <binary-data>
                   ::= [x20-x2f] <binary-data>
                   ::= [x34-x37] b0 <binary-data>
        '''
        bvalue = value.value
        
        while len(value) > 65535 :
            self.__write('\x41')
            self.__pack('>H', 65535)
            self.__write(value[:65535])
            value = value[65535:]

        if len(value) <= 15 :
            self.__writeByte(0x20 + len(value))
        elif len(value) <= 1023 :
            self.__writeByte(0x34 + value >> 8)
            self.__write(value & 0xff)
        else :
            self.__write('B')
            self.__pack('>H', len(value))
        
        self.__write(value)

    def __addClassDef(self, value) :
        classDefId = 0
        type = value._metaType

        for classDef in self.classDefs :
            if type == classDef.type :
                return classDefId
            classDefId += 1

        self.__write('C')
        self.__mWriteObject(type)

        fieldNames = value.__dict__.keys()
        fieldNames.remove('_metaType')
        
        self.__encodeInt(len(fieldNames))
        for fieldName in fieldNames :
            self.__mWriteObject(fieldName)

        self.classDefs.append(ClassDef(type, fieldNames))

        return len(self.classDefs) - 1

    @encoderFor(Object)
    def __encodeObject(self, value) :
        if self.__addRef(value) :
            return

        classDefId = self.__addClassDef(value)

        if classDefId <= 15 :
            self.__writeByte(0x60 + classDefId)
        else :
            self.__write('O')
            self.__encodeInt(classDefId)

        for fieldName in self.classDefs[classDefId].fieldNames :
            self.__mWriteObject(value.__dict__[fieldName])

DECODERS = [None] * 256

def decodeFor(codes) :
    def register(f) :
        for code in codes :
            if type(code) == types.IntType :
                DECODERS[code] = f
            elif type(code) == types.TupleType and len(code) == 2:
                for i in range(code[0], code[1] + 1) :
                    DECODERS[i] = f
        return f
    return register

    

class Hessian2Input(object) :
    def __init__(self, bytes) :
        self.input = StringIO(bytes)
        self.types = []
        self.classDefs = []
        self.refs = []
    def readObject(self) :
        #pdb.set_trace()
        return self.__mReadObject(self.__readByte())

    def __readByte(self) :
        c = self.input.read(1)
        if c == '' :
            raise ValueError('End Of Byte String')
        return ord(c)

    def __read(self, num = 1) :
        c = self.input.read(num)
        if len(c) < num :
            raise ValueError('End Of Byte String')
        return c

    def __mReadObject(self, code) :
        while True :
            if code < 0 or code > 255 :
                raise ValueError('code %x is unexpected when read object')
            decoder = DECODERS[code]
            if decoder == None :
                raise ValueError('code %x is not support')
            result = decoder(self, code)
            if result == None and code == ord('C') :
                code = self.__readByte()
                continue
            return result

    @decodeFor((ord('N'),))
    def __decodeNull(self, code) :
        if __debug :
            print 'read None'
        return None

    @decodeFor((ord('F'), ord('T')))
    def __decodeBoolean(self, code) :
        if __debug :
            print 'read boolean :', code == 0x54
        return code == 0x54

    @decodeFor(((0x80, 0xbf), (0xc0, 0xcf), (0xd0, 0xd7), ord('I')))
    def __decodeInt(self, code) :
        result = 0
        if 0x80 <= code <= 0xbf :
            result = code - 0x90
        elif 0xc0 <= code <= 0xcf :
            i = (code - 0xc8) << 8
            i |= self.__readByte()
            result = i
        elif 0xd0 <= code <= 0xd7 :
            i = (code - 0xd4) << 16
            i |= self.__readByte() << 8
            i |= self.__readByte()
            result = i
        else :
            result = struct.unpack('>i', self.__read(4))[0]
        if __debug :
            print 'read int :', result
        return result
            
    @decodeFor(((0xd8, 0xef), (0xf0, 0xff), (0x38, 0x3f), 0x59, ord('L')))
    def __decodeLong(self, code) :
        result = 0
        if 0xd8 <= code <= 0xef :
            result = code - 0xe0
        elif 0xf0 <= code <= 0xff :
            result = ((code - 0xf8) << 8) | self.__readByte()
        elif 0x38 <= code <= 0x3f :
            i = (code - 0x3c) << 16
            i |= self.__readByte() << 8
            i |= self.__readByte()
            result = i
        elif code == 0x59 :
            result = struct.unpack('>i', self.__read(4))[0]
        else :
            result = struct.unpack('>q', self.__read(8))[0]
        if __debug :
            print 'read long :', result
        return result

    @decodeFor((0x5b, 0x5c, 0x5d, 0x5e, 0x5f, ord('D')))
    def __decodeFloat(self, code) :
        result = 0.0
        if code == 0x5b :
            result = 0.0
        elif code == 0x5c :
            result = 1.0
        elif code == 0x5d :
            result = float(struct.unpack('>b', self.__read(1))[0])
        elif code == 0x5e :
            result = float(struct.unpack('>h', self.__read(2))[0])
        elif code == 0x5f :
            result = struct.unpack('>f', self.__read(4))[0]
        else :
            result = struct.unpack('>d', self.__read(8))[0]
        if __debug :
            print 'read float :', result
        return result

    @decodeFor((0x4a, 0x4b))
    def __decodeDate(self, code) :
        result = None
        if code == 0x4a :
            timei = struct.unpack('>q', self.__read(8))[0]
            ts = time.localtime(timei/1000)
            milliseconds = timei % 1000
            result = datetime.datetime(ts.tm_year, ts.tm_mon, ts.tm_mday, ts.tm_hour, ts.tm_min, ts.tm_sec, milliseconds * 1000)
        else :
            timei = struct.unpack('>i', self.__read(4))[0]
            ts = time.localtime(timei * 60)
            result = datetime.datetime(ts.tm_year, ts.tm_mon, ts.tm_mday, ts.tm_hour, ts.tm_min)
        if __debug :
            print 'read date :', result
        return result

    def __readUTF(self, output, length) :
        while length > 0 :
            c = self.__readByte()
            output.write(chr(c))
            if c < 0x80 :
                pass
            elif (c & 0xe0) == 0xc0 :
                output.write(self.__read(1))
            elif (c & 0xf0) == 0xe0 :
                output.write(self.__read(2))
            elif (c & 0xf8) == 0xf0 :
                output.write(self.__read(3))
            length -= 1
        
    @decodeFor((0x52, ord('S'), (0x00, 0x1f), (0x30, 0x33)))
    def __decodeString(self, code) :
        buf = StringIO()
        while code == 0x52 :
            length = struct.unpack('>H', self.__read(2))[0]
            self.__readUTF(buf, length)
            code = self.__readByte()

        length = 0
        if code == ord('S') :
            length = struct.unpack('>H', self.__read(2))[0]
        elif 0x00 <= code <= 0x1f :
            length = code
        else :
            length = (code - 0x30) << 8 | self.__readByte()
        
        self.__readUTF(buf, length)
        result = buf.getvalue().decode('utf-8')
        if __debug :
            print 'read string :', result
        return result

    def __decodeType(self) :
        code = self.__readByte()
        if code == 0x52                     \
            or code == ord('S')             \
            or (0x00 <= code <= 0x1f)       \
            or (0x30 <= code <= 0x33) :

            type = self.__decodeString(code)
            if type == '' :
                raise ValueError('type string is empty')
            self.types.append(type)
            if __debug :
                print 'read type :', type
            return type
        elif code == ord('I')               \
            or (0x80 <= code <= 0xbf)       \
            or (0xc0 <= code <= 0xcf)       \
            or (0xd0 <= code <= 0xd7) :
            
            typeId = self.__decodeInt(code)
            if typeId < 0 or typeId >= len(self.types) :
                raise ValueError('type id %d undefined' % (typeId,))
            if __debug :
                print 'read type ref :', typeId, self.types[typeId]
            return self.types[typeId]
        else :
            raise ValueError('code %x is unexpected when decode type')

    @decodeFor((0x55, 0x57))
    def __decodeList(self, code) :
        if code == 0x55 :
            self.__decodeType()
        
        result = []
        c = self.__readByte()
        while c != ord('Z') :
            result.append(self.__mReadObject(c))
            c = self.__readByte()
    
        self.refs.append(result)
        if __debug :
            print 'read list :', result
        return result

    @decodeFor((ord('V'), 0x58, (0x70, 0x77), (0x78, 0x7f)))
    def __decodeTuple(self, code) :
        result = []

        if code == ord('V') or (0x70 <= code <= 0x77) :
            self.__decodeType()

        length = 0
        if 0x70 <= code <= 0x77 :
            length = code - 0x70
        elif 0x78 <= code <= 0x7f :
            length = code - 0x78
        else :
            length = self.__decodeInt(self.__readByte())
        
        while length > 0 :
            result.append(self.__mReadObject(self.__readByte()))
            length -= 1

        result = tuple(result)
        self.refs.append(result)
        if __debug :
            print 'read tuple :', result
        return result

    @decodeFor((ord('H'), ord('M')))
    def __decodeDict(self, code) :
        result = {}

        if code == ord('M') :
            self.__decodeType()

        c = self.__readByte()
        while c != ord('Z') :
            key = self.__mReadObject(c)
            value = self.__mReadObject(self.__readByte())
            result[key] = value
            c = self.__readByte()

        self.refs.append(result)
        if __debug :
            print 'read dict :', result
        return result

    @decodeFor((0x41, ord('B'), (0x20, 0x2f), (0x34, 0x37)))
    def __decodeBinary(self, code) :
        result = Binary(None)
        while code == 0x41 :
            length = struct.unpack('>H', self.__read(2))[0]
            result += Binary(self.__read(length))
            code = self.__readByte()
        
        length = 0
        if code == ord('B') :
            length = struct.unpack('>H', self.__read(2))[0]
        elif 0x20 <= code <= 0x2f :
            length = code - 0x20
        else :
            length = ((code - 0x34) << 8) | self.__readByte()

        if length > 0 :
            result += Binary(self.__read(length))
        
        if __debug :
            print 'read Binary :', result
        return result

    @decodeFor((ord('C'),))
    def __decodeClassDef(self, code) :
        type = self.__decodeString(self.__readByte())
        length = self.__decodeInt(self.__readByte())

        fieldNames = []
        while length > 0 :
            fieldNames.append(self.__decodeString(self.__readByte()))
            length -= 1
        self.classDefs.append(ClassDef(type, fieldNames))

        if __debug :
            print 'read ClassDef :', ClassDef(type, fieldNames)
        return None

    @decodeFor((ord('O'), (0x60, 0x6f)))
    def __decodeObject(self, code) :
        defId = -1
        if code == ord('O') :
            defId = self.__decodeInt(self.__readByte())
        else :
            defId = code - 0x60
        if defId >= len(self.classDefs) :
            raise ValueError('classDef id %d is undefined' % (defId,))
        
        result = {}
        cDef = self.classDefs[defId]
        if __debug :
            print 'start read Object : defId =', defId, 'type =', cDef.type
        for key in cDef.fieldNames :
            result[key] = self.__mReadObject(self.__readByte())
            if __debug :
                print 'read Object field :', key, ' =', result[key]
        
        self.refs.append(result)

        if __debug :
            print 'read Object :', result
        return Object(cDef.type, result)

    @decodeFor((0x51,))
    def __decodeRef(self, code) :
        refId = self.__decodeInt(self.__readByte())
        if refId >= len(self.refs) :
            raise ValueError('ref id %d is undefined' % (refId,))

        if __debug :
            print 'read ref :', refId
        return self.refs[refId]

if __name__ == '__main__' :
    '''
    a = {'b':1, 'a':'cfdfdfd', 'c':[1, 2, 3], 'd':u'你好'}
    print a

    output = Hessian2Output()
    output.writeObject(a)
    byteStr = output.getByteString()
    printByteStr(byteStr)

    input = Hessian2Input(byteStr)

    b = input.readObject()
    print b'''
    data = '''
    43 30 27 63 6f 6d 2e 71 75 6e 61 72 2e 74 72 
    61 76 65 6c 2e 62 6f 6f 6b 2e 6d 6f 64 65 6c 32 
    2e 54 72 61 76 65 6c 42 6f 6f 6b b8 02 69 64 06 
    75 73 65 72 49 64 0a 74 65 6d 70 55 73 65 72 49 
    64 08 75 73 65 72 4e 61 6d 65 09 6c 61 62 65 6c 
    4e 61 6d 65 08 64 65 73 74 4e 61 6d 65 05 74 69 
    74 6c 65 0c 70 61 70 65 72 43 6f 6e 74 65 6e 74 
    0b 70 68 6f 6e 65 4e 75 6d 62 65 72 04 6d 65 6d 
    6f 08 63 69 74 79 4e 61 6d 65 07 70 75 62 6c 69 
    73 68 0a 70 75 62 6c 69 73 68 4e 75 6d 0b 64 6f 
    77 6e 6c 6f 61 64 4e 75 6d 0c 73 6f 75 72 63 65 
    42 6f 6f 6b 49 64 06 73 74 61 74 75 73 06 70 65 
    72 6d 69 74 05 73 63 6f 72 65 02 69 70 0c 63 6f 
    72 65 50 72 6f 76 69 6e 63 65 05 65 6d 61 69 6c 
    08 69 6d 61 67 65 55 72 6c 06 63 69 74 79 49 64 
    06 61 62 72 6f 61 64 04 61 72 65 61 09 72 6f 75 
    74 65 44 61 79 73 0c 63 6f 6d 6d 65 6e 74 43 6f 
    75 6e 74 0e 72 65 63 6f 6d 6d 65 6e 64 43 6f 75 
    6e 74 0d 71 75 65 73 74 69 6f 6e 43 6f 75 6e 74 
    09 62 65 73 74 44 61 79 49 64 09 73 74 61 72 74 
    54 69 6d 65 05 63 54 69 6d 65 05 75 54 69 6d 65 
    11 74 72 61 76 65 6c 42 6f 6f 6b 44 61 79 4c 69 
    73 74 0c 63 69 74 79 49 6e 66 6f 4c 69 73 74 0e 
    74 72 61 76 65 6c 43 69 74 79 4c 69 73 74 13 74 
    72 61 76 65 6c 43 69 74 79 52 6f 75 74 65 4c 69 
    73 74 0a 63 6f 6c 6c 65 63 74 44 61 79 0a 64 65 
    73 74 43 69 74 69 65 73 0c 6f 6c 64 42 6f 6f 6b 
    4d 6f 64 65 6c 60 59 00 0a 90 67 59 07 3b bc 50 
    4e 08 72 75 74 67 31 31 36 35 4e 4e 06 e6 88 91 
    e7 9a 84 e6 97 85 e8 a1 8c e6 94 bb e7 95 a5 4e 
    0b 31 33 36 30 30 34 30 38 39 34 30 4e 4e 54 90 
    90 e0 90 54 49 00 2d f2 38 0d 31 31 34 2e 32 31 
    36 2e 32 33 2e 35 36 4e 4e 4e 90 46 90 90 90 90 
    90 e0 4b 01 58 6a 00 4a 00 00 01 3b 52 51 9b f8 
    4a 00 00 01 3b 52 51 9b f8 78 78 4e 78 4e 4e 43 
    30 26 63 6f 6d 2e 71 75 6e 61 72 2e 74 72 61 76 
    65 6c 2e 62 6f 6f 6b 2e 6d 6f 64 65 6c 2e 54 72 
    61 76 65 6c 42 6f 6f 6b b8 02 69 64 06 75 73 65 
    72 49 64 0a 74 65 6d 70 55 73 65 72 49 64 08 75 
    73 65 72 4e 61 6d 65 09 6c 61 62 65 6c 4e 61 6d 
    65 08 64 65 73 74 4e 61 6d 65 05 74 69 74 6c 65 
    0c 70 61 70 65 72 43 6f 6e 74 65 6e 74 0b 70 68 
    6f 6e 65 4e 75 6d 62 65 72 04 6d 65 6d 6f 08 63 
    69 74 79 4e 61 6d 65 07 70 75 62 6c 69 73 68 0a 
    70 75 62 6c 69 73 68 4e 75 6d 0b 64 6f 77 6e 6c 
    6f 61 64 4e 75 6d 0c 73 6f 75 72 63 65 42 6f 6f 
    6b 49 64 06 73 74 61 74 75 73 06 70 65 72 6d 69 
    74 05 73 63 6f 72 65 02 69 70 0c 63 6f 72 65 50 
    72 6f 76 69 6e 63 65 05 65 6d 61 69 6c 08 69 6d 
    61 67 65 55 72 6c 06 63 69 74 79 49 64 06 61 62 
    72 6f 61 64 04 61 72 65 61 08 69 6e 74 65 67 72 
    61 6c 09 72 6f 75 74 65 44 61 79 73 0c 63 6f 6d 
    6d 65 6e 74 43 6f 75 6e 74 0e 72 65 63 6f 6d 6d 
    65 6e 64 43 6f 75 6e 74 0d 71 75 65 73 74 69 6f 
    6e 43 6f 75 6e 74 09 62 65 73 74 44 61 79 49 64 
    0a 70 68 6f 74 6f 43 6f 75 6e 74 09 73 74 61 72 
    74 54 69 6d 65 05 63 54 69 6d 65 05 75 54 69 6d 
    65 11 74 72 61 76 65 6c 42 6f 6f 6b 44 61 79 4c 
    69 73 74 0e 74 72 61 76 65 6c 43 69 74 79 4c 69 
    73 74 0a 63 6f 6c 6c 65 63 74 44 61 79 0a 64 65 
    73 74 43 69 74 69 65 73 05 6d 54 69 6d 65 61 59 
    00 0a 90 67 59 07 3b bc 50 4e 08 72 75 74 67 31 
    31 36 35 4e 4e 06 e6 88 91 e7 9a 84 e6 97 85 e8 
    a1 8c e6 94 bb e7 95 a5 4e 0b 31 33 36 30 30 34 
    30 38 39 34 30 4e 4e 54 90 90 e0 90 54 49 00 2d 
    f2 38 0d 31 31 34 2e 32 31 36 2e 32 33 2e 35 36 
    4e 4e 4e 90 46 90 90 90 90 90 90 e0 90 4b 01 58 
    6a 00 4a 00 00 01 3b 52 51 9b f8 4a 00 00 01 3b 
    52 51 9b f8 78 4e 4e 4e 4e
    '''

    data = data.split()
    data = [chr(eval('0x' + num)) for num in data]
    data = ''.join(data)
    print len(data)
    printByteStr(data)

    input = Hessian2Input(data)

    print input.readObject()

