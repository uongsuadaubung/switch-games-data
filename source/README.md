# Đây là thư mục chứa file ZIP nguồn
# GitHub Actions sẽ đọc file `latest.zip` từ thư mục này

# File ZIP sẽ được bỏ qua bởi git (xem .gitignore)
# nhưng khi bạn force-push, Action vẫn trigger vì `.github/workflows/parse.yml`
# watch path `source/latest.zip`
