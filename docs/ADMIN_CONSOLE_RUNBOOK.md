# Admin console runbook

Muc tieu: van hanh cac viec co ban bang menu, khong can nho lenh.

## Cach mo

Chay file:

```text
Z:\Tools\KhoiDongAdminConsole.bat
```

Menu gom:

```text
1. Healthcheck he thong
2. Backup database ngay
3. QCVL bridge dry-run
4. Xem log bridge QCVL
5. Xuat mau payload QCVL bridge
6. Kiem tra moi truong Python
7. Kiem tra code/script
8. Chay unit test
9. Preflight truoc deploy
10. Build ban moi vao dist-new
11. Publish ban moi (co backup + rollback)
12. Rollback ve ban cu
13. Restore database tu backup
14. Tao goi chan doan cho AI
15. Cai lich backup tu dong
16. Xem ke hoach tong
17. Xem ke hoach V2
18. Kiem tra san sang V2
19. Bat V2 mode (tat Auto_CRM/Zalo auto)
20. Ve legacy mode
21. V2 preflight truoc publish
22. Start V2 runtime (server + dashboard, khong Auto_CRM)
0. Thoat
```

## Muc an toan

Muc `11. Publish ban moi` bat go chu:

```text
DEPLOY
```

Muc `12. Rollback ve ban cu` bat go chu:

```text
ROLLBACK
```

Muc `13. Restore database tu backup` bat go chu:

```text
RESTORE
```

De tranh bam nham.

Muc `19. Bat V2 mode` bat go chu:

```text
V2
```

Muc `20. Ve legacy mode` bat go chu:

```text
LEGACY
```

Muc `22. Start V2 runtime` bat go chu:

```text
V2START
```

## Nen dung khi nao

- Truoc deploy: chon `1`, `2`, `9`.
- Truoc build: chon `7`.
- Unit test rieng: chon `8`.
- Preflight truoc deploy: chon `9`.
- Build ban moi: chon `10`.
- Sau deploy: chon `1`.
- Khi nghi QCVL bridge co van de: chon `3`, `4`.
- Khi can xuat mau du lieu cho QCVL: chon `5`.
- Khi ban moi loi: chon `12`.
- Khi can khoi phuc DB: chon `13`.
- Khi can AI xem loi nhanh: chon `14`.
- Khi muon bat backup tu dong hang ngay: chon `15`.
- Khi muon xem lo trinh V2: chon `17`.
- Khi muon kiem tra may da cau hinh theo V2 chua: chon `18`.
- Khi da san sang tat Auto_CRM/Zalo auto sau khi restart app: chon `19`.
- Khi can quay ve hanh vi cu: chon `20`.
- Truoc khi publish V2: chon `21`.
- Khi muon chay server/dashboard theo V2 mode sau khi da publish/build: chon `22`.
