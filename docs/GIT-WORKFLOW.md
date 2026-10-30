# Git workflow and review policy

[README](../README.md) · [Working agreements](WORKING-AGREEMENTS.md)

## Branch strategy

Dùng một `main` chung và short-lived feature branches. Mỗi team phát triển trong directory của mình; không tạo long-lived branch theo team hoặc tuần. Mọi thay đổi vào `main` đi qua Pull Request (PR), kể cả documentation và tracker.

Branch name: `<type>/<scope>/<task>`, với type là `feat`, `fix`, `docs`, `test`, `chore`; scope là `team-4.1`, `team-4.2` hoặc `shared`.

Ví dụ: `feat/team-4.1/w02-table-parser`, `docs/team-4.2/w03-report`, `docs/shared/evaluation-rubric`.

## Ownership and approval matrix

| Scope | Paths | Required approval | Merge owner |
|---|---|---|---|
| Team 4.1 | `app/`, `data/`, `evals/`, `experiments/`, `scripts/`, `teams/` dưới `team-4.1/`; `weeks/*/team-4.1-TRACKER.md`; `reports/*/team-4.1/` | Một reviewer thuộc Team 4.1, khác author | Integration owner của Team 4.1 |
| Team 4.2 | Các paths tương ứng của Team 4.2 | Một reviewer thuộc Team 4.2, khác author | Integration owner của Team 4.2 |
| Shared | Root files, `docs/`, `templates/`, `.github/`, weekly README, các index/README chung và file ngoài team scope | Mentor/maintainer, khác author; nếu ảnh hưởng cả hai team, thêm một representative mỗi team | Mentor/maintainer |
| Cross-team | Thay đổi đồng thời files thuộc hai team | Một reviewer mỗi team, đều khác author; thêm mentor nếu có shared scope | Mentor/maintainer |

Một người có thể giữ nhiều vai trò nhưng không tự approve PR của mình. Nếu merge owner là author, nhờ reviewer đủ quyền hoặc mentor merge sau khi đủ approval. Team chỉ định integration owner và backup mỗi tuần; mặc định là người phụ trách UI/tích hợp. Mentor chỉ định backup maintainer để review PR do mentor tạo.

Nếu PR chỉ cần sửa sản phẩm một team, tách thay đổi shared không liên quan sang PR khác. Owner thư mục thể hiện trách nhiệm review, không phải quyền riêng tư: thành viên có quyền truy cập repo vẫn có thể đọc nội dung của cả hai team.

## Task → branch → PR → merge

1. Tạo issue hoặc task trong tracker: team, tuần, acceptance criteria, owner, reviewer, dependencies và scope.
2. Đồng bộ `main`, tạo branch riêng. Đảm bảo working tree sạch trước khi switch/merge; commit công việc đang làm vào branch phù hợp trước.
3. Commit nhỏ, đúng scope. Kiểm tra staged diff, không dùng `git add .` một cách máy móc.
4. Push branch và mở Draft PR sớm nếu cần feedback. PR target là `main`.
5. Chạy validation phù hợp, ghi reproduction steps và evidence. Chuyển Ready for review, request reviewers theo matrix.
6. Reviewer đọc diff, kiểm tra acceptance criteria và yêu cầu sửa nếu còn blocker. Author phản hồi và push commit bổ sung; thay đổi nội dung sau approval cần re-review.
7. Merge owner đồng bộ với `main` mới nhất, bảo đảm approval còn phù hợp, conversations đã resolve và checks liên quan pass. Dùng **Squash and merge** để một PR có một commit rõ nghĩa trên `main`.
8. Cập nhật task/issue và tracker. Nếu chưa cập nhật tracker trong PR, mở documentation PR nhỏ sau merge; không push trực tiếp `main`. Chỉ đóng task sau khi acceptance criteria đã đạt.

Reviewer phản hồi trong một ngày làm việc; nếu bị chặn, liên hệ backup/integration owner. Không giảm yêu cầu approval chỉ để kịp demo.

## Command walkthrough

Các lệnh dưới là hướng dẫn sau khi maintainer đã tạo initial commit, cấu hình `origin` và push `main`; không phải trạng thái đã thiết lập trên remote. Thay branch/file mẫu bằng task thực.

```bash
git status
git switch main
git pull --ff-only origin main
git switch -c feat/team-4.1/w02-table-parser

# Sau khi chỉnh sửa file cụ thể
git add app/team-4.1/README.md
git diff --cached
git commit -m "docs(team-4.1): describe ingestion setup"
git push -u origin feat/team-4.1/w02-table-parser
```

Mở PR qua giao diện Git hosting và dùng PR template. Mỗi người dùng tài khoản Git riêng để lưu authorship và review history.

## Conflict resolution

Đồng bộ trên feature branch, không giải quyết conflict trực tiếp trên `main`:

```bash
git fetch origin
git merge origin/main
# Sửa từng conflicted file, giữ đúng thay đổi của cả hai phía
git status
git add path/to/resolved-file
git commit
git push
```

Chỉ chạy `git commit` trong ví dụ khi merge đang chờ xử lý conflict. Nếu merge tự hoàn tất thì không cần commit thêm. Khi chưa hiểu conflict, dùng `git merge --abort` để dừng merge và nhờ owner file hỗ trợ. Không chọn hàng loạt “ours/theirs”. Chạy lại checks bị ảnh hưởng và request re-review sau khi resolve.

Không force-push branch dùng chung. Workflow này dùng merge từ `main` để người mới không phải rewrite history.

## Review checklist

- Scope đúng team; thay đổi shared/cross-team được ghi rõ và có đủ reviewers.
- Hành vi đáp ứng acceptance criteria; code rõ ràng, error handling phù hợp.
- Reproduction steps chạy được; validation evidence có commit/config/snapshot khi cần.
- Thay đổi retrieval/generation có evaluation phù hợp; documentation-only kiểm tra links và nội dung.
- Không có secrets, PII thực, dataset lớn hoặc generated index trong diff.
- README/config/lockfile liên quan đã cập nhật; không thay dependency dùng chung ngoài scope.
- Không còn unresolved blocking feedback; approval áp dụng cho phiên bản cuối.

## Remote protection setup — maintainer checklist

Đây là **policy và checklist**, chưa phải cấu hình đã áp dụng. Hiện repo chưa được thiết lập remote protection hay CI bởi tài liệu này.

Khi có GitHub remote, maintainer kiểm tra tính năng khả dụng của repo và cấu hình `main`:

- Require a pull request và ít nhất một approving review.
- Dismiss stale approvals khi có thay đổi mới; require conversation resolution.
- Chặn force push/deletion; không dùng bypass cho công việc hằng ngày.
- Khi có CI chạy ổn định, thêm required status checks tương ứng; không yêu cầu tên check chưa tồn tại.
- Cấu hình CODEOWNERS bằng GitHub usernames/teams thực và bật required code owner review nếu phù hợp. Chưa tạo CODEOWNERS với account giả.

Branch protection có thể enforce review và status checks; xem [GitHub protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).

**Approval matrix vẫn cần merge owner kiểm tra:** số approval tối thiểu không tự bảo đảm đúng đại diện từng team. Với nhiều owners cho cùng path, CODEOWNERS không yêu cầu tất cả cùng approve; xem [GitHub CODEOWNERS](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners). Nếu cần enforce đầy đủ matrix, bổ sung automation sau khi có danh sách account và hosting cụ thể.

## Weekly release and rollback

Sau nghiệm thu, merge owner tạo annotated tag trên **commit đã demo và được chấp nhận**, ghi cùng SHA vào báo cáo. Tag có prefix team dù Git tag đánh dấu snapshot của toàn repo.

```bash
# Thay ACCEPTED_COMMIT_SHA bằng SHA đã được nghiệm thu
git tag -a team-4.1/week-01-demo ACCEPTED_COMMIT_SHA -m "Team 4.1 Week 1 accepted demo"
git push origin team-4.1/week-01-demo
```

Không ghi đè tag đã công bố; dùng `-v2` nếu nghiệm thu bản sửa. Tag code không thay thế dataset/index snapshot.

Nếu một PR đã merge gây lỗi, tạo fix hoặc revert PR qua cùng review policy. Với squash commit, có thể dùng `git revert <commit-sha>` trên branch sửa lỗi. Không `reset --hard` hay force-push `main`; xác minh revert không phá thay đổi tiếp theo của team còn lại.
