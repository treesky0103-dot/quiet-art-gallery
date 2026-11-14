#!/usr/bin/env python3
"""Fail-closed artifact upload budget guard for no-payment GitHub Free users.

A public repository's compute can be free while its Actions artifact storage
is metered. Avoid uploading proofs if current non-expired repository artifact
storage is at or above a conservative 300 MiB limit.
"""
import json
import os
from urllib.request import Request, urlopen
from urllib.parse import urlencode

MAX_REPO_ARTIFACT_STORAGE = 300 * 1024 * 1024
MAX_NEW_UPLOAD = 1_500_000
REPO = "treesky0103-dot/quiet-art-gallery"

def budget(token):
    total=0
    for page in range(1,51):
        url=f"https://api.github.com/repos/{REPO}/actions/artifacts?"+urlencode({"per_page":100,"page":page})
        req=Request(url,headers={
            "Authorization":"Bearer "+token,
            "Accept":"application/vnd.github+json",
            "X-GitHub-Api-Version":"2022-11-28",
            "User-Agent":"quiet-art-gallery-storage-safety"})
        with urlopen(req,timeout=20) as response:
            obj=json.load(response)
        entries=obj.get("artifacts")
        if not isinstance(entries,list):raise RuntimeError("Malformed artifact response")
        for art in entries:
            if not art.get("expired"):total+=int(art.get("size_in_bytes") or 0)
        if total+MAX_NEW_UPLOAD>MAX_REPO_ARTIFACT_STORAGE:return False,total
        if len(entries)<100:return True,total
    return False,total # fail closed when page limit reached

def main():
    token=os.environ.get("GH_TOKEN","")
    allowed=False
    current=None
    try:
        if not token:raise ValueError("no auth")
        allowed,current=budget(token)
    except Exception as e:
        print("ARTIFACT_BUDGET_CHECK_UNAVAILABLE "+str(e)[:180],flush=True)
    print("ARTIFACT_STORAGE_BUDGET allow="+str(allowed).lower()+
          " total_bytes="+str(current)+" maximum_bytes="+str(MAX_REPO_ARTIFACT_STORAGE),flush=True)
    output=os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output,"a",encoding="utf-8") as f:
            f.write("allow_upload="+str(allowed).lower()+"\n")
            f.write("current_bytes="+str(current or 0)+"\n")

if __name__=="__main__":
    main()
