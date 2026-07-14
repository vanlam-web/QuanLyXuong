# Ke hoach deploy co rollback

Muc tieu: co the dua ban moi vao xuong, neu loi thi quay ve ban cu trong vai phut.

## Nguyen tac

- Khong deploy truc tiep tu code dang sua.
- Moi ban moi phai nam trong mot thu muc rieng, vi du `dist-new`.
- Truoc khi thay `dist`, luu lai toan bo `dist` hien tai vao `releases\rollback-YYYYMMDD-HHMMSS`.
- Neu ban moi loi, chay rollback de copy lai ban cu vao `dist`.
- Khong de mat khau, PIN, group Zalo, NAS credential trong script deploy.

## Cau truc release

```text
Z:\Tools
  dist\                         Ban dang duoc may xuong copy/chay
  dist-new\                     Ban moi vua build, dung de publish
  releases\
    rollback-20260709-153000\   Ban cu duoc backup truoc deploy
      dist\
      manifest.json
    20260709-153000\            Ban moi da publish
      dist\
      manifest.json
```

`releases\` bi ignore trong Git vi chua file exe lon.

## Deploy ban moi

1. Build ban moi ra mot thu muc rieng, khuyen nghi `Z:\Tools\dist-new`.
2. Dam bao trong thu muc do co cac file exe can deploy:

```text
QuanLyXuong.exe
server.exe
Dashboard.exe
bridge_qcvl.exe
Auto_CRM.exe
```

3. Chay:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Publish-Release.ps1 -NewDistPath Z:\Tools\dist-new
```

Script se:

- Backup database `C:\QuanLyXuong\Data` vao `Z:\Tools\backups\data\pre-release-*`.
- Kiem tra du file exe.
- Backup `Z:\Tools\dist` hien tai vao `Z:\Tools\releases\rollback-...`.
- Luu mot ban copy cua ban moi vao `Z:\Tools\releases\...`.
- Copy ban moi vao `Z:\Tools\dist`.
- Tao manifest checksum de doi chieu.

Neu can bo qua backup DB trong truong hop dac biet:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Publish-Release.ps1 -NewDistPath Z:\Tools\dist-new -SkipDataBackup
```

## Rollback khi loi

Neu ban moi lam anh huong cong viec, chay:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Rollback-Release.ps1
```

Mac dinh script se lay backup rollback moi nhat trong `Z:\Tools\releases\rollback-*`.

Neu muon chi dinh ro ban backup:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Rollback-Release.ps1 -RollbackPath Z:\Tools\releases\rollback-20260709-153000
```

Script se:

- Luu lai `dist` hien tai vao `releases\failed-...`.
- Copy ban rollback vao `dist`.
- Ghi `dist\CURRENT_RELEASE.json`.

## Luu y van hanh

- Nen deploy vao luc xuong it viec.
- Sau deploy, neu client/server dang chay co co che auto update theo mtime cua exe thi chung co the tu restart.
- Neu rollback xong ma tien trinh chua cap nhat, khoi dong lai service/bat tren may do.
- Luon giu it nhat 1 ban rollback gan nhat.
