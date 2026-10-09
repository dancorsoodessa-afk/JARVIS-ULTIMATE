"""Compatibility helpers selected from older JARVIS projects."""

def smart_launch(name: str) -> str:
    import difflib, subprocess, os
    query=str(name).strip().lower()
    if not query: raise ValueError("Укажите название приложения.")
    out=subprocess.run(["powershell","-NoProfile","-Command",'Get-StartApps | Sort-Object Name | ForEach-Object { "$($_.Name)|$($_.AppID)" }'],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=8).stdout
    apps=[]
    for line in out.splitlines():
        if "|" in line:
            title,appid=line.split("|",1)
            if title.strip(): apps.append((title.strip(),appid.strip()))
    if not apps:
        from agent.tools.apps import launch_needs_confirmation
        if launch_needs_confirmation(name):
            raise ValueError("Список приложений недоступен; запуск по пути или с аргументами через smart_launch запрещён. Используйте launch с подтверждением.")
        os.startfile(name)
        return f"Запускаю: {name}"
    names=[x[0] for x in apps]
    match=difflib.get_close_matches(query,names,n=1,cutoff=0.35)
    if not match: raise ValueError(f"Приложение «{name}» не найдено.")
    title=match[0]
    subprocess.Popen(["explorer.exe",f"shell:AppsFolder\\{dict(apps)[title]}"])
    return f"Запускаю: {title}"
