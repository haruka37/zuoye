"""系统类工具：获取日期时间、闰年判断等。

只依赖标准库，与文件系统无关。
"""

import platform
import subprocess


def getDate():
    """获取当前电脑的日期和时间（调用本地 date 系统命令，不用 time/datetime）。"""
    if platform.system().lower() == "windows":
        result = subprocess.run(
            ["cmd", "/c", "date /t & time /t"],
            capture_output=True,
        )
        text = result.stdout.decode("gbk", errors="replace")
        return text.strip().replace("\r", " ").replace("\n", " ")
    else:
        result = subprocess.run(["date"], capture_output=True)
        return result.stdout.decode("utf-8", errors="replace").strip()


def isLeapYear(year):
    """判断输入的年份是否为闰年（用 Python 代码计算）。"""
    year = int(year)
    leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
    return f"{year} 是闰年" if leap else f"{year} 不是闰年"
