#!/usr/bin/env python3
"""Post a truthful result for EACH completed GitHub collection attempt to issue #2.

ChatGPT cannot deliver 10-minute push notifications itself; GitHub Issues has
subscription notifications controlled by the user's GitHub notification settings.
"""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen

REPO="treesky0103-dot/quiet-art-gallery"
ISSUE=2

def status_message(run_id, job_status, report, state, proof_upload='unknown'):
    now=datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M KST")
    valid=(isinstance(report,dict) and str(report.get("github_run_id"))==str(run_id))
    successful=job_status=="success" and valid and state is not None
    count=int(report.get("new_verified_this_run",0)) if successful else 0
    total=int(state.get("claimed_total_with_requested_baseline",0)) if successful else None
    increment=int(state.get("new_verified",0)) if successful else None
    if successful and (total!=736+increment or count<0):
        raise ValueError("Ledger inconsistencies; refusing numerical report")
    label="수집·검증 성공" if successful else "작업 실패 또는 검증 보류"
    total_text=str(total)+"점" if total is not None else "확인 불가"
    lines=[f"@treesky0103-dot  **{now} · {label}**",
           f"- 이번 회차 신규 검증: **+{count}점**" if successful else "- 이번 회차 신규 검증: **확정 불가(실패/보류)**",
           f"- 누적 기준 합계: **{total_text}** (사용자 지정 736점 + 검증된 추가분)",
           f"- Github 실행: https://github.com/{REPO}/actions/runs/{run_id}"]
    if successful:
        lines.extend([f"- 이번 다운로드 시도: {report.get('download_attempts',0)}회, 자료조회 페이지: {report.get('scan_pages',0)}",
              f"- 전체 검증 파일 중 단기 증빙용 샘플: {report.get('proof_files',0)}개, {report.get('proof_bytes',0)} bytes",
              f"- 해시·원본 URL만 장기 보관한 파일: {report.get('verified_only_in_hash_ledger',0)}개",
              "- 샘플 ZIP 업로드: "+("성공(1일 후 만료)" if proof_upload=="success" else "미실행·실패(저장 용량 상한 등 확인 필요)"),
              "- **주의:** 각 파일의 실제 다운로드·디코딩 검사는 수행하되, 샘플을 제외한 이미지 파일은 해당 실행이 끝나면 삭제됩니다. 태블릿에는 자동 저장되지 않습니다."])
    else:
        lines.append("- 수집 엔진·원본 제공처·업로드 또는 GitHub 인증에 문제가 생겼을 수 있습니다. 이전 누적 실적은 유지됩니다.")
    return "\n".join(lines)+"\n"

def main():
    run_id=os.environ["GITHUB_RUN_ID"]
    job_status=os.environ.get("GALLERY_JOB_STATUS","unknown")
    p=Path("collector-10min-batch/report.json")
    sp=Path("data/collector_10min/state.json")
    report=json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
    state=json.loads(sp.read_text(encoding="utf-8")) if sp.is_file() else None
    msg=status_message(run_id,job_status,report,state,os.environ.get("PROOF_UPLOAD_OUTCOME","unknown"))
    summary=os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary,"a",encoding="utf-8") as f:
            f.write("## 10분 수집 결과\n\n"+msg+"\n")
    print("NOTIFICATION_BODY "+msg.replace("\n"," | "),flush=True)
    token=os.environ.get("GH_TOKEN")
    if not token:raise RuntimeError("No GITHUB_TOKEN; result retained in job summary but Issue comment not sent")
    url=f"https://api.github.com/repos/{REPO}/issues/{ISSUE}/comments"
    payload=json.dumps({"body":msg},ensure_ascii=False).encode("utf-8")
    req=Request(url,data=payload,headers={
        "Authorization":"Bearer "+token,"Accept":"application/vnd.github+json",
        "Content-Type":"application/json","X-GitHub-Api-Version":"2022-11-28",
        "User-Agent":"quiet-art-gallery-collector-notifier"},method="POST")
    with urlopen(req,timeout=20) as res:
        obj=json.load(res)
        if res.status!=201 or not obj.get("id"):raise RuntimeError("Issue comment not confirmed")
        print("GITHUB_ISSUE_COMMENT_CONFIRMED "+str(obj["id"])+" "+str(obj.get("html_url","")),flush=True)

def selftest():
    s={"new_verified":4,"claimed_total_with_requested_baseline":740}
    r={"github_run_id":"123","new_verified_this_run":1,"download_attempts":4,"scan_pages":3,"proof_files":1,"proof_bytes":34567}
    assert "+1점" in status_message("123","success",r,s)
    assert "740점" in status_message("123","success",r,s)
    assert "확정 불가" in status_message("123","failure",r,s)
    assert "확정 불가" in status_message("321","success",r,s)
    print("NOTIFICATION_SELFTEST_PASS")

if __name__=="__main__":
    import sys
    if "--self-test" in sys.argv:selftest()
    else:main()
