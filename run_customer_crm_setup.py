from __future__ import annotations
import argparse
from datetime import datetime
from pathlib import Path

def update_env(path:Path,key:str,value:str):
    lines=path.read_text(encoding='utf-8').splitlines() if path.exists() else []; prefix=f'{key}='; found=False; out=[]
    for line in lines:
        if line.strip().startswith(prefix): out.append(f'{key}={value}'); found=True
        else: out.append(line)
    if not found: out.append(f'{key}={value}')
    path.write_text('\n'.join(out)+'\n',encoding='utf-8')

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument('--env',default='.env'); p.add_argument('--enable-phone',action='store_true'); args=p.parse_args()
    if not args.enable_phone: print('No changes made. Use --enable-phone after explicit CRM approval.'); return 0
    path=Path(args.env); backup=path.with_name(f"{path.name}.backup.customer5.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    if path.exists(): backup.write_bytes(path.read_bytes())
    update_env(path,'MEMORY_STORE_PHONE','true'); print('Operational CRM phone persistence enabled.'); print(f'Updated: {path.resolve()}'); print(f'Backup: {backup.resolve()}'); print('No secret values were displayed.'); return 0
if __name__=='__main__': raise SystemExit(main())
