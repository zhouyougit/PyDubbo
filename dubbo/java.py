import zipfile
import os
import struct

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

MAGIC_NUMBER = 0xCAFEBABE

CONSTANT_UTF8 = 1
CONSTANT_INTEGER = 3
CONSTANT_FLOAT = 4
CONSTANT_LONG = 5
CONSTANT_DOUBLE = 6
CONSTANT_CLASS = 7
CONSTANT_STRING = 8
CONSTANT_FIELDREF = 9
CONSTANT_METHODREF = 10
CONSTANT_INTERFACE_METHODREF = 11
CONSTANT_NAME_AND_TYPE = 12

ACC_PUBLIC      = 0x0001
ACC_PRIVATE     = 0x0002
ACC_PROTECTED   = 0x0004
ACC_STATIC      = 0x0008
ACC_FINAL       = 0x0010
ACC_SYNCHRONIZED= 0x0020
ACC_SUPER       = 0x0020
ACC_VOLATILE    = 0x0040
ACC_TRANSIENT   = 0x0080
ACC_NATIVE      = 0x0100
ACC_INTERFACE   = 0x0200
ACC_ABSTRACT    = 0x0400
ACC_STRICT      = 0x0800

CONSTANT_DEFINE = (None, \
        'utf8', \
        None, \
        '>i', \
        '>f', \
        '>q', \
        '>d', \
        '>H', \
        '>H', \
        '>HH', \
        '>HH', \
        '>HH', \
        '>HH')

class JavaClass(object) :
    def __init__(self, input = None, classFileName = None) :
        if input != None :
            self.input = input
        elif classFileName != None :
            self.input = file(classFileName)
        else :
            raise ValueError('input and fileName None')
        self.__readClass()
        self.__postProcess()
        del self.input

    def __postProcess(self) :
        self.methodMap = {}
        for method in self.methods :
            name = self.__getString(method['nameIndex'])
            if name in self.methodMap :
                self.methodMap[name].append(method)
            else :
                self.methodMap[name] = [method]

    def __readUShort(self) :
        return struct.unpack('>H', self.input.read(2))[0]

    def __getClassName(self, index) :
        nameIndex = self.constantPool[index][1]
        return self.__getString(nameIndex).replace('/', '.')

    def __getString(self, index) :
        return self.constantPool[index][2]

    def __readClass(self) :
        self.magic, self.minor, self.major = struct.unpack('>IHH', self.input.read(8))
        if self.magic != MAGIC_NUMBER :
            raise ValueError('this is not java class file')

        self.__decodeConstant()

        self.accessFlags = self.__readUShort()

        self.thisClass = self.__getClassName(self.__readUShort())

        self.superClass = self.__getClassName(self.__readUShort())

        self.__decodeInterfaces()

        self.__decodeFields()

        self.__decodeMethods()

        self.attributes = self.__decodeAttributes()


    def __decodeConstant(self) :
        constantPoolCount = self.__readUShort()

        constantPool = [None]
        while constantPoolCount > 1 :   #len(constantPool) = constantPoolCount - 1
            type = ord(self.input.read(1))
            if type == CONSTANT_UTF8 :
                length = self.__readUShort()
                value = self.input.read(length)
                constant = [type, length, value]
            else :
                defStr = CONSTANT_DEFINE[type]
                length = struct.calcsize(defStr)
                constant = list(struct.unpack(defStr, self.input.read(length)))
                constant.insert(0, type)
            constantPool.append(constant)
            constantPoolCount -= 1
        self.constantPool = constantPool
    
    def __decodeInterfaces(self) :
        interfacesCount = self.__readUShort()
        self.interfaces = []
        for i in range(interfacesCount) :
            self.interfaces.append(self.__getClassName(self.__readUShort()))

    def __decodeFields(self) :
        fieldsCount = self.__readUShort()
        self.fields = []
        for i in range(fieldsCount) :
            field = {}
            field['accessFlags'] = self.__readUShort()
            field['nameIndex'] = self.__readUShort()
            field['descriptorIndex'] = self.__readUShort()
            field['attributeInfo'] = self.__decodeAttributes()
            self.fields.append(field)

    def __decodeMethods(self) :
        methodsCount = self.__readUShort()
        self.methods = []
        for i in range(methodsCount) :
            method = {}
            method['accessFlags'] = self.__readUShort()
            method['nameIndex'] = self.__readUShort()
            method['descriptorIndex'] = self.__readUShort()
            method['attributeInfo'] = self.__decodeAttributes()
            self.methods.append(method)

    def __decodeAttributes(self) :
        attributesCount = self.__readUShort()
        attributes = []
        for i in range(attributesCount) :
            attribute = {}
            attribute['attributeNameIndex'] = self.__readUShort()
            attribute['attributeLength'] = struct.unpack('>I', self.input.read(4))[0]
            attribute['info'] = self.input.read(attribute['attributeLength'])

        return attributes

    def __str__(self) :
        ps = 'JavaClass : ' + str(self.__dict__)
        return ps


class JarLoader(object) :
    def __init__(self, fileName) :
        self.zfobj = zipfile.ZipFile(fileName)
        self.classDefs = {}

    def getClassDef(self, className) :
        classFileName = className.replace('.', '/') + '.class'
        if classFileName in self.classDefs :
            return self.classDefs[classFileName]
        else :
            try :
                classData = self.zfobj.read(classFileName)
            except KeyError :
                return None
            input = StringIO(classData)
            classDef = JavaClass(input = input)
            self.classDefs[classFileName] = classDef
            return classDef

JAVA_CLASS_TYPE_MAP = { \
        'java.lang.String' : 'string', \
        'java.lang.Boolean' : 'bool', \
        'java.lang.Byte' : 'byte', \
        'java.lang.Character' : 'string', \
        'java.lang.Double' : 'float', \
        'java.lang.Float' : 'float', \
        'java.lang.Integer' : 'int', \
        'java.lang.Long' : 'long', \
        'java.lang.Short' : 'int', \
        'java.util.Collection' : 'list', \
        'java.util.Date' : 'date', \
        'java.util.HashMap' : 'dict', \
        'java.util.HashSet' : 'list', \
        'java.util.List' : 'list', \
        'java.util.Map' : 'dict', \
        'java.util.Set' : 'list', \
        'java.util.TreeMap' : 'dict', \
        'java.util.TreeSet' : 'list', \
        'java.util.Vector' : 'list'}

def analyseParamTypes(types) :
    result = []
    offset = 0
    while offset < len(types) :
        t = ''
        c = types[offset]
        offset += 1
        while c == '[' :
            t += '['
            c = types[offset]
            offset += 1

        if c == 'V' :
            t += 'void'
        elif c == 'Z' :
            t += 'bool'
        elif c == 'B' :
            t += 'byte'
        elif c == 'C' :
            t += 'string'
        elif c == 'D' or c == 'F' :
            t += 'float'
        elif c == 'I' or c == 'S' :
            t += 'int'
        elif c == 'J' :
            t += 'long'
        elif c == 'L' :
            objName = ''
            c = types[offset]
            offset += 1
            while c != ';' :
                objName += c
                c = types[offset]
                offset += 1
            objName = objName.replace('/', '.')
            if objName in JAVA_CLASS_TYPE_MAP :
                t += JAVA_CLASS_TYPE_MAP[objName]
            else :
                t += objName
        else :
            raise ValueError(c + ' is unexpected in ParamType')

        result.append(t)
    return result

class JavaClassLoader(object) :
    def __init__(self, classPath = None) :
        self.classMap = {}
        if classPath == None :
            classPath = os.getenv('PD_CLASSPATH')
        if not classPath :
            raise EnvironmentError('java class path is empty')
        self.__analyseClassPath(classPath)

    def __analyseClassPath(self, classPath) :
        tempPaths = classPath.replace(';', ':').split(':')
        self.classPath = []
        for path in tempPaths :
            path = os.path.realpath(path)
            if path.endswith('.jar') :
                self.classPath.append(path)
            elif os.path.isdir(path) :
                self.classPath.append(path)

    def findClass(self, className) :
        if className in self.classMap :
            return self.classMap[className]

        input =  self.__findClassInput(className)
        if input == None :
            return None
        try :
            classInfo = JavaClass(input)
        finally :
            input.close()

        if classInfo != None :
            self.classMap[className] = classInfo
        return classInfo

    def __findClassInput(self, className) :
        classFileName = className.replace('.', '/') + '.class'
        for path in self.classPath :
            if os.path.isdir(path) :
                tempPath = os.path.join(path, classFileName)
                if os.path.isfile(tempPath) :
                    return file(tempPath)
            else :
                jarFile = zipfile.ZipFile(path)
                try :
                    classData = jarFile.read(classFileName)
                except KeyError :
                    continue
                finally :
                    jarFile.close()
                return StringIO(classData)
        return None


if __name__ == '__main__' :
    javaClassLoader = JavaClassLoader('.:travel-service-interface-1.5.3.jar')
    classDef = javaClassLoader.findClass('com.qunar.travel.book.service.ITravelBookService2')
    print classDef
    print '-----------'
    classDef = javaClassLoader.findClass('ITravelBookService2')
    print classDef

