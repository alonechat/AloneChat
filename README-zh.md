# AloneChat 项目

这个项目是一个简单的聊天系统，目前只有聊天室，后期会来考虑加上更多花里胡哨的功能

## 起因

这个项目其实就是我们想做啥就做做的，也没啥明确的起因。

### 命名

这个名字有点意思。Alone，独自的意思。
什么是“独自聊天”？一个人聊天？对的。
我们在开发这个软件的时候没法大规模测试，
只能自己跟自己开着三个终端，一个服务器，两个客户端，
然后再在两个客户端上分别发消息，再互换，检查，debug。

您看，是不是就是一个人聊天？

这个`AloneChat`的名字，便是这么得来的……

### 开发者（一开始的）

额，这个说起来就比较简单了，两名同学，中学生。

- 张同学，主要负责的是架构、UI，EMAIL: `<zhang dot chenyun at outlook dot com>`
- 陶同学，主要负责的是功能、组件

这个目前看上去没什么问题，
并且打算就这么一直用下去，直到这个软件出现一些状况，
不管是火了还是凉了，如果有状况可以第一时间联系我俩。

## 项目

项目的简介前面已经述及到了，这里就不再复制了。

这里可以给大家提供一些有意思的小细节：

1. 这个项目曾经重置过。一开始是在2024.8开始开发的，
   结果开发出来就是一堆冒着热气的垃圾（张同学背大锅）。
   当时的仓库还不在这儿，是在`alonechat/AloneChat.Frame`。
2. 2025.7.9 重置的。重置后焕然一新。
   URL改成了`alonechat/AloneChat`。
   之前叫Frame是因为之前本来是想把框架和内容分开开发，但是没成功。
   这次索性合并成一个项目，~~方便快捷简单易懂~~。

### 功能

### 使用方法

#### 用户

1. 下载打包好的客户端（参见releases）。
2. 打开一个终端。
3. 输入如下：

- 如您需要开启服务器：

  Windows:
  ```powershell
  ./AloneChat.exe server --port=<your_port>
  ```
  Linux:
  ```bash
  ./AloneChat server --port=<your_port>
  ```

- 如您需要开启客户端：
  Windows:
  ```powershell
  ./AloneChat.exe client --host=<your_host> --port=<your_port>
  ```
  Linux:
  ```bash
  ./AloneChat client --host=<your_host> --port=<your_port>
  ```

#### 开发者

```bash
git clone https://github.com/alonechat/AloneChat
cd AloneChat
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt # 如果需要打包
python . server   # 打开服务器
python . client   # 打开客户端
python packing.py # 打包为exe
```

### 分支

采用`canary`+`develop`+`master`分支策略。

- `canary`: 非常不稳定。测试用分支，二位同学会进场在此处添加不稳定的功能，
  所以用这个分支的人
  *有且仅限*
    - **明白每段代码是在干什么** *或/和*
    - **明白每个错误是如何引起** *或/和*
    - **知道大部分错误是如何修复**

  的软件开发者/爱好者 _*和/或*_ 专业人士。
  新功能爱好者先别着急，请移步至`develop`分支一探究竟。
- `develop`: 比较？稳定？No.不稳定。但是相比`canary`之下要好得多。
  新功能爱好者可以尝试这个分支的的代码。前提是需要一定的`Python`编程基础，
  方便使用这些代码。原因很简单，我们并不会打包`develop`分支的代码。
- `master`: 比较稳定。用户们可以选择下载这一分支。
  我们不建议开发者们使用这一分支，因为更新周期长。

分支和使用者的对应关系参见下表。

| 用户  | `canary` | `develop` | `master` |
|-----|----------|-----------|----------|
| 开发者 | ✅        | ⚠️        | ❌        |
| 爱好者 | ❌        | ✅         | ⚠️       |
| 用户  | ❌        | ❌         | ✅        |

### 打包

我们的代码欢迎任何一个开发者打包，所以创建了专门的打包脚本——
`packing.py`！任何人都可以使用，前提是安装好所有的依赖。安装方式：

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt # 打包所用
```

## 贡献

如果您想贡献一点代码，那可真是——太好啦！！！
非常感谢任何一名开发者为这个项目所作出任何一丁点贡献。

如果您有什么金点子，欢迎写入README，让它成为我们下一步的开发目标。
如果你发现了什么bug，欢迎提起issue。
如果你有更好的代码、或是想为我们做一点开发，
欢迎fork我们的代码，并提起PR！

## 致谢

非常感谢任何一名开发者为这个项目所作出任何一丁点贡献。
哪怕是写一个文档、修一个typo，我们都将以最热忱的感激之情，报答您的付出！

## LICENSE

我们的`LICENSE`采用`Apache License Version 2.0`，详情请见`LICENSE`文件。
