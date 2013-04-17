PyDubbo
=======

这是一个python实现的dubbo服务调用的客户端

协议支持
------------
由于dubbo支持多种协议扩展，目前只开发了dubbo服务的默认协议：dubbo+hessian2的支持
其它协议的支持慢慢来吧

安装
--------

运行环境
-----------
由于dubbo协议的限制，所以进行远程调用需要接口的参数类型列表，所以客户端需要读取dubbo接口的java class文件来获取参数类型列表

示例
----------
        config = { 'classpath' : '%classpath%' }
        client = Dubbo(('localhost', 20880), config)
        remoteService = client.getProxy('com.test.RemoteService')

        print remoteService.getTestInfo(123)

config 参考
-----------
Dubbo对象的config参数包含的内容比较丰富，目前支持的配置如下：

### owner
指定dubbo client的所有者
### customer
指定dubbo client名字
### classpath
指定dubbo远程接口对应的java class所在的路径，以冒号或者分号分隔
可以支持jar格式
该参数可以不指定，改为通过环境变量"PD_CLASSPATH"来指定,config的优先级高于环境变量
### reference
为一个dict，包含每一个具体接口的详细配置
'interfaceName' : referenceConfig

referenceConfig 参考
-----------------------
### async
该接口是否异步调用，调用示例：
        remoteService.getTestInfo(123)
        future1 = RpcContext.future
        remoteService.getTestInfo(124)
        future2 = RpcContext.future

        result1 = future1.get()
        result2 = future2.get()

### withReturn
该接口是否需要等待返回值，如果为False则不等待接口返回。

### method
为一个dict，包含接口中每一个方法的具体配置
'methodName' : methodConfig

### timeout
接口调用超时时间, 单位秒，可以为浮点数

methodConfig 参考
----------------------
### async
同 referenceConfig 的async
### withReturn
同 referenceConfig 的withReturn
### timeout
同 referenceConfig 的timeout

