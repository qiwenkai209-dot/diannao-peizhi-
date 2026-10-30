::[Bat To Exe Converter]
::
::YAwzoRdxOk+EWAjk
::fBw5plQjdG8=
::YAwzuBVtJxjWCl3EqQJgSA==
::ZR4luwNxJguZRRnk
::Yhs/ulQjdF+5
::cxAkpRVqdFKZSDk=
::cBs/ulQjdF+5
::ZR41oxFsdFKZSTk=
::eBoioBt6dFKZSDk=
::cRo6pxp7LAbNWATEpCI=
::egkzugNsPRvcWATEpCI=
::dAsiuh18IRvcCxnZtBJQ
::cRYluBh/LU+EWAnk
::YxY4rhs+aU+JeA==
::cxY6rQJ7JhzQF1fEqQJQ
::ZQ05rAF9IBncCkqN+0xwdVs0
::ZQ05rAF9IAHYFVzEqQJQ
::eg0/rx1wNQPfEVWB+kM9LVsJDGQ=
::fBEirQZwNQPfEVWB+kM9LVsJDGQ=
::cRolqwZ3JBvQF1fEqQJQ
::dhA7uBVwLU+EWDk=
::YQ03rBFzNR3SWATElA==
::dhAmsQZ3MwfNWATElA==
::ZQ0/vhVqMQ3MEVWAtB9wSA==
::Zg8zqx1/OA3MEVWAtB9wSA==
::dhA7pRFwIByZRRnk
::Zh4grVQjdCyDJGyX8VAjFBZVTzimOXixEroM1G0qGmNBRMrpgWrbiQY+NzNT7tZApBWqcI4otg==
::YB416Ek+Zm8=
::
::
::978f952a14a936cc963da21a135fa983
@echo off
chcp 936 >nul
color 07
net session >nul 2>&1
if %errorlevel% NEQ 0 (
    echo 请求管理员权限...
    PowerShell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)
title 展馆系统配置工具
:MAIN
cls
echo ┌──────────────────────────────────────────────┐
echo │               展馆系统配置工具               │
echo ├──────────────────────────────────────────────┤
echo │ A UAC控制        1关闭｜10恢复               │
echo │ B Defender策略   2关闭｜20恢复               │
echo │ C Windows更新    3关闭｜30恢复               │
echo │ D 系统防火墙     4关闭｜40开启               │
echo │ E 网卡节能       5关闭｜50恢复               │
echo │ F IP地址模式     6静态｜60DHCP自动           │
echo │ G 快速启动       7关闭｜70开启               │
echo │ H 触摸手势       8禁用｜80恢复               │
echo │ I 电源休眠       9永不休眠｜90默认            │
echo │ J RDP远程桌面  101开启无密码｜102关闭         │
echo ├──────────────────────────────────────────────┤
echo │ K 打开网络面板                               │
echo │ M 打开启动文件夹                             │
echo │ R 重启电脑                                   │
echo ├──────────────────────────────────────────────┤
echo │ ALLON 展馆一键配置（自动执行K+M，最后重启确认）│
echo │ ALLOFF 恢复系统默认                          │
echo │ H帮助   Q退出                                │
echo └──────────────────────────────────────────────┘
set /p opt=请输入操作选项：

if /i "%opt%"=="Q" exit
if /i "%opt%"=="H" goto HELP
if /i "%opt%"=="R" goto REBOOT
if /i "%opt%"=="ALLON" set opt=1 2 3 4 5 6 7 8 9 101
if /i "%opt%"=="ALLOFF" set opt=10 20 30 40 50 60 70 80 90 102

for %%o in (%opt%) do (
    echo.
    echo ----------------------------------------------
    echo 正在执行：%%o
    echo ----------------------------------------------
    if "%%o"=="1" (
        reg ADD "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v EnableLUA /t REG_DWORD /d 0 /f
        echo UAC已关闭，重启生效
    )
    if "%%o"=="10" (
        reg ADD "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v EnableLUA /t REG_DWORD /d 1 /f
        echo UAC已恢复，重启生效
    )
    if "%%o"=="2" (
        reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows Defender" /v DisableAntiSpyware /t REG_DWORD /d 1 /f
        echo Defender策略已关闭，家庭版无效
    )
    if "%%o"=="20" (
        reg delete "HKLM\SOFTWARE\Policies\Microsoft\Windows Defender" /v DisableAntiSpyware /f >nul 2>&1
        echo Defender策略已恢复默认
    )
    if "%%o"=="3" (
        reg add HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU /v NoAutoUpdate /t REG_DWORD /d 1 /f
        echo Windows自动更新已关闭
    )
    if "%%o"=="30" (
        reg delete HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU /v NoAutoUpdate /f >nul 2>&1
        echo Windows自动更新已恢复
    )
    if "%%o"=="4" (
        netsh advfirewall set allprofiles state off
        echo 防火墙全部关闭
    )
    if "%%o"=="40" (
        netsh advfirewall set allprofiles state on
        echo 防火墙全部开启
    )
    if "%%o"=="5" (
        powercfg /changevalueindex SUB_NET 0003 0000
        echo 网卡节能已关闭
    )
    if "%%o"=="50" (
        powercfg /changevalueindex SUB_NET 0003 0001
        echo 网卡节能已恢复
    )
    if "%%o"=="6" (
        netsh interface ip set address "以太网" static 192.168.10.11 255.255.255.0 192.168.10.1
        netsh interface ip set dns "以太网" static 192.168.10.1
        netsh interface ip add dns "以太网" 114.114.114.114 index=2
        echo 以太网静态IP配置完成：192.168.10.11
    )
    if "%%o"=="60" (
        netsh interface ip set address "以太网" dhcp
        netsh interface ip set dns "以太网" dhcp
        echo 以太网恢复DHCP自动获取
    )
    if "%%o"=="7" (
        reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power" /v HiberbootEnabled /t REG_DWORD /d 0 /f
        echo 快速启动关闭，重启生效
    )
    if "%%o"=="70" (
        reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power" /v HiberbootEnabled /t REG_DWORD /d 1 /f
        echo 快速启动开启，重启生效
    )
    if "%%o"=="8" (
        reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Touch" /v DisableEdgeUI /t REG_DWORD /d 1 /f
        reg add "HKCU\Software\Synaptics\SynTPEnh" /v DisableGestures /t REG_DWORD /f
        echo 触摸手势已禁用
    )
    if "%%o"=="80" (
        reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Touch" /v DisableEdgeUI /f >nul 2>&1
        reg delete "HKCU\Software\Microsoft\Windows\Synaptics\SynTPEnh" /v DisableGestures /f >nul 2>&1
        echo 触摸手势已恢复
    )
    if "%%o"=="9" (
        powercfg /change monitor-timeout-ac 0
        powercfg /change standby-timeout-ac 0
        echo 电源设置：永不关闭显示器、永不休眠
    )
    if "%%o"=="90" (
        powercfg /change monitor-timeout-ac 60
        powercfg /change standby-timeout-ac 30
        echo 电源恢复系统默认超时
    )
    if "%%o"=="101" (
        reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 0 /f
        reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp" /v UserAuthentication /t REG_DWORD /d 0 /f
        reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v PasswordOptional /t REG_DWORD /d 1 /f
        echo RDP无密码登录已开启，仅限内网使用
    )
    if "%%o"=="102" (
        reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 1 /f
        reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp" /v UserAuthentication /t REG_DWORD /d 1 /f
        reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v PasswordOptional /f >nul 2>&1
        echo RDP远程桌面已关闭
    )
    if /i "%%o"=="K" (
        start ncpa.cpl
        echo 已打开网络连接面板
    )
    if /i "%%o"=="M" (
        explorer "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
        echo 已打开启动文件夹
    )
)

:: ALLON执行完毕自动执行K、M，再进入重启确认
if /i "%optinput%"=="ALLON" goto POST_ALL
if /i "%opt%"=="1 2 3 4 5 6 7 8 9 101" goto POST_ALL
goto END_OP

:POST_ALL
echo.
echo ==============================================
echo ALLON批量配置完成，执行K、M
echo 打开网络面板、启动文件夹
echo ==============================================
start ncpa.cpl
explorer "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
echo.
goto REBOOT

:END_OP
echo.
echo **** 操作完成，部分设置需要重启系统生效 ****
echo.
echo 按任意键返回主菜单
pause >nul
goto MAIN

:REBOOT
cls
echo ┌──────────────────────────────────────────────┐
echo │              确认重启电脑？                   │
echo ├──────────────────────────────────────────────┤
echo │ 输入 Y 确认重启，其他按键取消                 │
echo └──────────────────────────────────────────────┘
set /p confirm=请选择：
if /i "%confirm%"=="Y" (
    echo 系统即将重启...
    shutdown /r /t 3 /c "展馆配置工具重启"
) else (
    echo 已取消重启
    pause >nul
)
goto MAIN

:HELP
cls
echo ┌──────────────────────────────────────────────┐
echo │                  使用帮助                     │
echo ├──────────────────────────────────────────────┤
echo │ 1.脚本必须【以管理员身份运行】               │
echo │ 2.保存文件编码选择ANSI，防止中文乱码         │
echo │ 3.K打开网络面板，M打开启动文件夹              │
echo │ 4.ALLON展馆一键配置：                        │
echo │   批量执行完成自动运行K(网络面板)+M(启动文件夹)│
echo │   然后弹出重启确认                            │
echo │ 5.ALLOFF恢复系统默认                          │
echo │ 6.UAC、快速启动修改后需要重启电脑生效        │
echo │ 7.RDP无密码模式仅用于展馆内网工控机          │
echo │ 8.R选项：单独重启电脑，带确认提示             │
echo └──────────────────────────────────────────────┘
echo.
echo 按任意键返回菜单
pause >nul
goto MAIN
@echo off
chcp 936 >nul
color 07
net session >nul 2>&1
if %errorlevel% NEQ 0 (
    echo 请求管理员权限...
    PowerShell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)
title 展馆系统配置工具
:MAIN
cls
echo ┌──────────────────────────────────────────────┐
echo │               展馆系统配置工具               │
echo ├──────────────────────────────────────────────┤
echo │ A UAC控制        1关闭｜10恢复               │
echo │ B Defender策略   2关闭｜20恢复               │
echo │ C Windows更新    3关闭｜30恢复               │
echo │ D 系统防火墙     4关闭｜40开启               │
echo │ E 网卡节能       5关闭｜50恢复               │
echo │ F IP地址模式     6静态｜60DHCP自动           │
echo │ G 快速启动       7关闭｜70开启               │
echo │ H 触摸手势       8禁用｜80恢复               │
echo │ I 电源休眠       9永不休眠｜90默认            │
echo │ J RDP远程桌面  101开启无密码｜102关闭        │
echo ├──────────────────────────────────────────────┤
echo │ K 打开网络面板                               │
echo │ M 打开启动文件夹                             │
echo │ R 重启电脑                                   │
echo ├──────────────────────────────────────────────┤
echo │ ALLON 展馆一键配置   ALLOFF 恢复系统默认     │
echo │ H帮助   Q退出                                │
echo └──────────────────────────────────────────────┘
set /p opt=请输入操作选项：

if /i "%opt%"=="Q" exit
if /i "%opt%"=="H" goto HELP
if /i "%opt%"=="R" goto REBOOT
if /i "%opt%"=="ALLON" set opt=1 2 3 4 5 6 7 8 9 101
if /i "%opt%"=="ALLOFF" set opt=10 20 30 40 50 60 70 80 90 102

for %%o in (%opt%) do (
    echo.
    echo ----------------------------------------------
    echo 正在执行：%%o
    echo ----------------------------------------------
    if "%%o"=="1" (
        reg ADD "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v EnableLUA /t REG_DWORD /d 0 /f
        echo UAC已关闭，重启生效
    )
    if "%%o"=="10" (
        reg ADD "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v EnableLUA /t REG_DWORD /d 1 /f
        echo UAC已恢复，重启生效
    )
    if "%%o"=="2" (
        reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows Defender" /v DisableAntiSpyware /t REG_DWORD /d 1 /f
        echo Defender策略已关闭，家庭版无效
    )
    if "%%o"=="20" (
        reg delete "HKLM\SOFTWARE\Policies\Microsoft\Windows Defender" /v DisableAntiSpyware /f >nul 2>&1
        echo Defender策略已恢复默认
    )
    if "%%o"=="3" (
        reg add HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU /v NoAutoUpdate /t REG_DWORD /d 1 /f
        echo Windows自动更新已关闭
    )
    if "%%o"=="30" (
        reg delete HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU /v NoAutoUpdate /f >nul 2>&1
        echo Windows自动更新已恢复
    )
    if "%%o"=="4" (
        netsh advfirewall set allprofiles state off
        echo 防火墙全部关闭
    )
    if "%%o"=="40" (
        netsh advfirewall set allprofiles state on
        echo 防火墙全部开启
    )
    if "%%o"=="5" (
        powercfg /changevalueindex SUB_NET 0003 0000
        echo 网卡节能已关闭
    )
    if "%%o"=="50" (
        powercfg /changevalueindex SUB_NET 0003 0001
        echo 网卡节能已恢复
    )
    if "%%o"=="6" (
        netsh interface ip set address "以太网" static 192.168.10.11 255.255.255.0 192.168.10.1
        netsh interface ip set dns "以太网" static 192.168.10.1
        netsh interface ip add dns "以太网" 114.114.114.114 index=2
        echo 以太网静态IP配置完成：192.168.10.11
    )
    if "%%o"=="60" (
        netsh interface ip set address "以太网" dhcp
        netsh interface ip set dns "以太网" dhcp
        echo 以太网恢复DHCP自动获取
    )
    if "%%o"=="7" (
        reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power" /v HiberbootEnabled /t REG_DWORD /d 0 /f
        echo 快速启动关闭，重启生效
    )
    if "%%o"=="70" (
        reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power" /v HiberbootEnabled /t REG_DWORD /d 1 /f
        echo 快速启动开启，重启生效
    )
    if "%%o"=="8" (
        reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Touch" /v DisableEdgeUI /t REG_DWORD /d 1 /f
        reg add "HKCU\Software\Synaptics\SynTPEnh" /v DisableGestures /t REG_DWORD /f
        echo 触摸手势已禁用
    )
    if "%%o"=="80" (
        reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Touch" /v DisableEdgeUI /f >nul 2>&1
        reg delete "HKCU\Software\Microsoft\Windows\Synaptics\SynTPEnh" /v DisableGestures /f >nul 2>&1
        echo 触摸手势已恢复
    )
    if "%%o"=="9" (
        powercfg /change monitor-timeout-ac 0
        powercfg /change standby-timeout-ac 0
        echo 电源设置：永不关闭显示器、永不休眠
    )
    if "%%o"=="90" (
        powercfg /change monitor-timeout-ac 60
        powercfg /change standby-timeout-ac 30
        echo 电源恢复系统默认超时
    )
    if "%%o"=="101" (
        reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 0 /f
        reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp" /v UserAuthentication /t REG_DWORD /d 0 /f
        reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v PasswordOptional /t REG_DWORD /d 1 /f
        echo RDP无密码登录已开启，仅限内网使用
    )
    if "%%o"=="102" (
        reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 1 /f
        reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp" /v UserAuthentication /t REG_DWORD /d 1 /f
        reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v PasswordOptional /f >nul 2>&1
        echo RDP远程桌面已关闭
    )
    if /i "%%o"=="K" (
        start ncpa.cpl
        echo 已打开网络连接面板
    )
    if /i "%%o"=="M" (
        explorer "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
        echo 已打开启动文件夹
    )
)

:: ALLON / ALLOFF全部执行完成后自动打开网络面板+启动文件夹，再进入重启确认
if /i "%opt%"=="ALLON" goto POST_ALL
if /i "%opt%"=="ALLOFF" goto POST_ALL
goto END_OP

:POST_ALL
echo.
echo ==============================================
echo 批量配置完成，自动打开网络面板、启动文件夹
echo ==============================================
start ncpa.cpl
explorer "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
echo.
goto REBOOT

:END_OP
echo.
echo **** 操作完成，部分设置需要重启系统生效 ****
echo.
echo 按任意键返回主菜单
pause >nul
goto MAIN

:REBOOT
cls
echo ┌──────────────────────────────────────────────┐
echo │              确认重启电脑？                   │
echo ├──────────────────────────────────────────────┤
echo │ 输入 Y 确认重启，其他按键取消                 │
echo └──────────────────────────────────────────────┘
set /p confirm=请选择：
if /i "%confirm%"=="Y" (
    echo 系统即将重启...
    shutdown /r /t 3 /c "展馆配置工具重启"
) else (
    echo 已取消重启
    pause >nul
)
goto MAIN

:HELP
cls
echo ┌──────────────────────────────────────────────┐
echo │                  使用帮助                     │
echo ├──────────────────────────────────────────────┤
echo │ 1.脚本必须【以管理员身份运行】               │
echo │ 2.保存文件编码选择ANSI，防止中文乱码         │
echo │ 3.K打开网络面板，M打开启动文件夹              │
echo │ 4.ALLON展馆一键配置 / ALLOFF恢复系统默认     │
echo │   批量执行完成自动打开网络面板+启动文件夹，  │
echo │   然后弹出重启确认                            │
echo │ 5.UAC、快速启动修改后需要重启电脑生效        │
echo │ 6.RDP无密码模式仅用于展馆内网工控机          │
echo │ 7.R选项：单独重启电脑，带确认提示             │
echo └──────────────────────────────────────────────┘
echo.
echo 按任意键返回菜单
pause >nul
goto MAIN
