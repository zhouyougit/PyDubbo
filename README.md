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
        client = Dubbo(('localhost', 20880), '%classpath%')
        #classpath为调用接口class文件的所在路径，支持jar格式，多个路径使用冒号分隔
        remoteService = client.getProxy('com.test.RemoteService')

        print remoteService.getTestInfo(123)

