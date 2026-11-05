# -*- coding: utf-8 -*-
"""Nội dung cửa sổ "Hướng dẫn sử dụng" (Tools → 📚 Hướng dẫn sử dụng).

Chỉ cần sửa chữ ở file này, không phải đụng vào main.py.
Mỗi mục là (tên tab, nội dung HTML). Viết bằng lời thường, tránh thuật ngữ.
"""

GEMINI_KEY_URL = "https://aistudio.google.com/api-keys"
GROQ_KEY_URL = "https://console.groq.com/keys"
POLLINATIONS_URL = "https://enter.pollinations.ai/keys"

GUIDE_SECTIONS = [
    ("🚀 Bắt đầu", f"""
<h2>Dùng lần đầu: 3 bước</h2>
<p>Lần đầu mở Anki sau khi cài add-on, add-on tự tạo sẵn cho bạn bộ thẻ <b>Gemini Vocabulary</b>, đã có mặt trước, mặt sau và giao diện đẹp.
Bạn không cần tự thiết kế thẻ. Nếu bộ thẻ của bạn đã có kiểu thẻ phù hợp từ trước thì add-on không tạo thêm.</p>
<ol>
  <li><b>Lấy chìa khoá (API key) miễn phí.</b> Đây là "thẻ thông hành" để add-on nhờ trí tuệ nhân tạo của Google soạn thẻ giúp bạn.
      Vào <a href="{GEMINI_KEY_URL}">{GEMINI_KEY_URL}</a>, đăng nhập Google và bấm tạo key, rồi copy lại.</li>
  <li><b>Dán key vào add-on.</b> Trong Anki chọn <b>Tools → Gemini Editor Settings…</b>, dán key vào ô
      "Google Gemini API Key" (mỗi dòng một key), rồi bấm <b>💾 Lưu cài đặt</b>.</li>
  <li><b>Thử một từ.</b> Mở cửa sổ <b>Add</b>, gõ từ cần học vào ô <b>Word</b>, rồi bấm nút <b>✨</b>
      (hoặc nhấn <b>Ctrl+G</b>). Vài giây sau, các ô còn lại sẽ được điền sẵn. Đọc lại, sửa nếu cần rồi bấm Add.</li>
</ol>
<p>Chỉ cần dán key <b>một lần</b> ở ô trên cùng. Hai ô còn lại (luyện câu và giọng đọc) cứ để trống thì add-on tự dùng
chung key đó, kể cả trên điện thoại (sau khi bấm Lưu và Sync).</p>
<p><b>Mẹo:</b> Key miễn phí chỉ dùng được một số lần mỗi ngày. Bạn có thể dán nhiều key, mỗi dòng một key.
Khi key này hết lượt, add-on tự chuyển sang key khác. Để tăng lượt thật sự, hãy tạo mỗi key ở một dự án Google khác nhau,
vì các key cùng một dự án dùng chung một hạn mức.</p>
"""),

    ("✍️ Thêm từng từ", """
<h2>Thêm một từ</h2>
<p>Gõ từ vào ô <b>Word</b> rồi bấm <b>✨</b> (hoặc <b>Ctrl+G</b>). Add-on sẽ điền: phiên âm, loại từ, nghĩa tiếng Anh và tiếng Việt,
câu ví dụ, từ đồng nghĩa, từ trái nghĩa, cụm từ hay đi kèm, bài tập... và vẽ một hình minh họa nếu bạn bật tính năng này.</p>

<h3>Nếu từ đã có trong bộ thẻ</h3>
<p>Add-on sẽ báo: <i>"Từ vựng [từ] này đã tồn tại trong bộ thẻ [tên bộ thẻ], vui lòng thêm từ khác."</i>
Lúc này add-on <b>không</b> nhờ AI soạn nữa, nên không tốn lượt dùng.</p>

<h3>Muốn nghĩa đúng ý mình</h3>
<p>Nhiều từ có nhiều nghĩa. Hãy ghi thêm gợi ý vào ô <b>Context</b> (ngữ cảnh) trước khi bấm ✨. Xem tab <b>🎯 Gợi ý nghĩa</b>.</p>

<h3>Nếu gõ sai chính tả</h3>
<p>Add-on sẽ nhận ra lỗi gõ sai thật (ví dụ <i>ohld</i> thay vì <i>hold</i>) và gợi ý từ đúng.
Từ đúng nhưng ở dạng số nhiều, quá khứ hay viết hoa thì không bị sửa.</p>
"""),

    ("📚 Thêm nhiều từ", """
<h2>Thêm nhiều từ cùng lúc</h2>
<p>Có hai cách, đều nằm trong menu <b>Tools</b> (hoặc nút <b>🚀</b> trên thanh công cụ):</p>
<ul>
  <li><b>✨ Thêm hàng loạt từ Gemini…</b> — dán danh sách từ (mỗi dòng một từ), chọn bộ thẻ rồi bấm chạy.
      Hợp với danh sách ngắn, khoảng vài chục từ.</li>
  <li><b>🚀 Thêm hàng loạt tối ưu…</b> — như trên nhưng có thêm lựa chọn: làm từng nhóm nhỏ, nghỉ giữa các nhóm,
      ghi chú ngữ cảnh dùng chung cho cả danh sách, và chọn kiểu thẻ.
      Hợp với danh sách dài.</li>
</ul>

<h3>Hai kiểu thẻ</h3>
<ul>
  <li><b>Thẻ nhẹ (nhanh, tiết kiệm):</b> chỉ gồm từ, phiên âm, loại từ và nghĩa. Từ nào đã có sẵn trong từ điển đi kèm add-on
      thì lấy luôn, <b>không tốn lượt AI nào</b>. Thẻ nhẹ không vẽ hình.</li>
  <li><b>Thẻ đầy đủ:</b> có thêm câu ví dụ, bài tập, hình minh họa... nên tốn nhiều lượt hơn.</li>
</ul>
<p>Thẻ nhẹ về sau vẫn nâng lên thành thẻ đầy đủ được: trong cửa sổ Browser, chọn thẻ rồi bấm chuột phải
→ <b>✨ Thêm chi tiết với Gemini</b>.</p>

<h3>Từ đã có sẽ được bỏ qua</h3>
<p>Trước khi chạy, add-on kiểm tra danh sách. Từ nào đã có trong bộ thẻ (hoặc bị gõ lặp lại trong danh sách) sẽ được bỏ qua
và hiện thông báo cho bạn biết. Các từ còn lại vẫn được thêm bình thường.</p>

<h3>Đang chạy mà bị dừng giữa chừng</h3>
<p>Mất mạng, hết lượt hoặc lỡ tắt Anki đều không sao. Vào <b>Tools → 🔄 Tiếp tục tiến trình bị gián đoạn</b>
để chạy tiếp từ chỗ đã dừng.</p>
"""),

    ("🔘 Các nút", """
<h2>Các nút trên thanh công cụ khi soạn thẻ</h2>
<table border="1" cellpadding="6" cellspacing="0" width="100%">
<tr><th>Nút</th><th>Bấm để làm gì</th></tr>
<tr><td>✨ &nbsp;(Ctrl+G)</td><td>Tự điền cả thẻ từ từ trong ô Word.</td></tr>
<tr><td>🚀</td><td>Mở cửa sổ thêm nhiều từ cùng lúc.</td></tr>
<tr><td>✅</td><td>Kiểm tra câu bạn tự đặt bằng từ đang học: đúng hay sai, và sai ở đâu.</td></tr>
<tr><td>💡</td><td>Gợi ý sửa câu của bạn cho tự nhiên hơn. Lời góp ý bằng tiếng Việt.</td></tr>
<tr><td>📖</td><td>Từ bài đọc bạn dán vào ô Reading, tìm ra các từ vựng đáng học.</td></tr>
<tr><td>🔗</td><td>Từ bài đọc đó, tìm thêm các từ liên quan để làm thẻ mới.</td></tr>
<tr><td>🔊 &nbsp;(Ctrl+Alt+Q)</td><td>Tạo giọng đọc (phát âm) cho thẻ.</td></tr>
<tr><td>🖼️ &nbsp;(Ctrl+Alt+I)</td><td>Chỉ vẽ lại hình minh họa, không làm lại cả thẻ.</td></tr>
<tr><td>🏷️</td><td>Tự gắn nhãn lĩnh vực (kinh doanh, y tế, luật...) và độ khó.</td></tr>
<tr><td>📝</td><td>Tạo bài tập dịch theo lĩnh vực bạn chọn.</td></tr>
<tr><td>🎧</td><td>Tạo bài tập nghe rồi nhắc lại, hoặc phiên dịch.</td></tr>
</table>
<p>Nếu không thấy các nút này, hãy tắt hẳn Anki rồi mở lại.</p>
"""),

    ("🎯 Gợi ý nghĩa", """
<h2>Gợi ý để add-on chọn đúng nghĩa</h2>
<p>Một từ có thể có nhiều nghĩa. Hãy ghi gợi ý vào ô <b>Context</b> (ngữ cảnh), hoặc gõ ngay sau từ.</p>

<h3>Cách 1: Nói từ này dùng ở đâu</h3>
<ul>
  <li><i>business meeting</i> — nghĩa trong cuộc họp công việc</li>
  <li><i>medical</i> — nghĩa trong ngành y</li>
  <li><i>education</i> — nghĩa trong giáo dục</li>
</ul>

<h3>Cách 2: Nói từ này là loại từ gì</h3>
<p>Ghi loại từ trong ngoặc vuông hoặc ngoặc tròn:</p>
<ul>
  <li><i>run [verb]</i> — chỉ lấy nghĩa động từ của "run"</li>
  <li><i>light [noun]</i> — chỉ lấy nghĩa danh từ</li>
  <li><i>fast [adj]</i> — chỉ lấy nghĩa tính từ</li>
  <li><i>quickly [adv]</i> — chỉ lấy nghĩa trạng từ</li>
</ul>
<p>Viết tắt được: <b>n</b> = danh từ, <b>v</b> = động từ, <b>adj</b> = tính từ, <b>adv</b> = trạng từ.</p>

<h3>Cách 3: Dùng cả hai</h3>
<ul><li><i>business meeting [noun]</i></li></ul>

<h3>Ví dụ cho người đi làm văn phòng</h3>
<ul>
  <li><i>stakeholder [noun]</i> — người có liên quan đến dự án</li>
  <li><i>buy-in</i> với ngữ cảnh <i>business</i> — sự đồng thuận, ủng hộ</li>
</ul>
"""),

    ("🖱️ Chuột phải", """
<h2>Dùng trong cửa sổ Browser</h2>
<p>Chọn một hoặc nhiều thẻ, bấm chuột phải để thấy:</p>
<ul>
  <li><b>✨ Thêm chi tiết với Gemini</b> — điền phần còn thiếu hoặc làm đầy đủ hơn cho các thẻ đã chọn
      (rất hợp để nâng thẻ nhẹ lên thẻ đầy đủ).</li>
  <li><b>🔗 Tạo từ vựng liên quan</b> — từ bài đọc trong mỗi thẻ, tìm thêm từ liên quan để làm thẻ mới.</li>
  <li><b>🚀 Add optimized vocabulary list</b> — chạy chế độ thêm hàng loạt tối ưu cho các thẻ đã chọn.</li>
</ul>
"""),

    ("🧰 Menu Tools", """
<h2>Các mục trong menu Tools</h2>
<table border="1" cellpadding="6" cellspacing="0" width="100%">
<tr><th>Mục</th><th>Dùng để làm gì</th></tr>
<tr><td>Gemini Editor Settings…</td><td>Nơi dán key, chọn model, chọn cách vẽ hình, cài đặt giọng đọc.</td></tr>
<tr><td>📊 Token Usage Statistics</td><td>Xem hôm nay bạn đã dùng bao nhiêu lượt, mỗi key một dòng.</td></tr>
<tr><td>🩺 Kiểm tra API key Gemini</td><td>Xem key nào còn dùng được, key nào hết lượt hoặc bị lỗi, và hôm nay còn thêm được khoảng bao nhiêu từ.</td></tr>
<tr><td>✨ Thêm hàng loạt từ Gemini…</td><td>Thêm một danh sách từ.</td></tr>
<tr><td>🚀 Thêm hàng loạt tối ưu…</td><td>Thêm danh sách dài, có nhiều lựa chọn hơn.</td></tr>
<tr><td>🔄 Tiếp tục tiến trình bị gián đoạn</td><td>Chạy tiếp danh sách đang thêm dở.</td></tr>
<tr><td>🔗 Tạo từ vựng liên quan từ bài đọc</td><td>Làm giống nút 🔗 cho thẻ đang mở.</td></tr>
<tr><td>📝 Cập nhật template cho tab Áp dụng</td><td>Thêm các ô còn thiếu để thẻ hiện được từ vựng lấy từ bài đọc. Chỉ cần chạy một lần.</td></tr>
<tr><td>⬆️ Upgrade Note Type</td><td>Thêm các ô còn thiếu cho bài tập dịch, bài tập nghe, lĩnh vực và độ khó. Chỉ cần chạy một lần.</td></tr>
<tr><td>🔄 Thêm nút bài tập dịch vào template</td><td>Thêm nút mở bài tập dịch lên mặt thẻ. Chạy sau mục ⬆️ ở trên.</td></tr>
<tr><td>🔊 Test phát hiện ngôn ngữ audio</td><td>Thử xem add-on nhận ra ngôn ngữ và chọn giọng đọc có đúng không. Dùng khi giọng đọc bị sai.</td></tr>
</table>
<p><b>Lưu ý:</b> ba mục cập nhật mẫu thẻ (📝, ⬆️, 🔄) sẽ sửa kiểu thẻ của bạn. Nên sao lưu Anki trước khi chạy.</p>
"""),

    ("🛠️ Khi gặp sự cố", f"""
<h2>Gặp sự cố thì làm gì?</h2>
<ul>
  <li><b>Báo "hết lượt" hoặc không soạn được thẻ:</b> key đã dùng hết lượt hôm nay.
      Thêm key mới (<a href="{GEMINI_KEY_URL}">{GEMINI_KEY_URL}</a>) hoặc đợi sang ngày hôm sau.
      Bấm <b>Tools → 🩺 Kiểm tra API key Gemini</b> để xem key nào còn dùng được.</li>
  <li><b>Vẫn hết lượt dù đã có nhiều key:</b> có thể các key cùng thuộc một dự án Google nên dùng chung hạn mức.
      Hãy tạo mỗi key ở một dự án khác nhau.</li>
  <li><b>Dùng dịch vụ Groq thay Gemini:</b> trong Settings, ở khung Groq, chọn Provider là <i>groq</i> và dán key lấy ở
      <a href="{GROQ_KEY_URL}">{GROQ_KEY_URL}</a>.</li>
  <li><b>Không có hình minh họa:</b> mở Settings, bật "Bật tính năng tự động tạo ảnh".
      Ở mục chọn engine, để <i>auto</i> là ổn nhất. Có hai nguồn vẽ hình:
      <b>AI Horde</b> miễn phí, không cần tài khoản nhưng hơi chậm (khoảng nửa phút đến một phút rưỡi);
      <b>Pollinations</b> vẽ đẹp và nhanh hơn nhưng tính tiền bằng "Pollen", cần có key.
      Lấy key ở <a href="{POLLINATIONS_URL}">{POLLINATIONS_URL}</a>. Bạn có thể nạp tiền, hoặc làm các nhiệm vụ
      (Quests) trên trang đó để nhận Pollen miễn phí. Hết Pollen thì hình vẽ sẽ tự chuyển sang AI Horde.</li>
  <li><b>Giọng đọc sai:</b> chạy <b>Tools → 🔊 Test phát hiện ngôn ngữ audio</b> để xem add-on nhận ra ngôn ngữ nào.</li>
  <li><b>Trên điện thoại, nút luyện câu không chạy:</b> đảm bảo đã có key ở ô trên cùng của Settings
      (ô "API dùng cho luyện câu" để trống cũng được), bấm Lưu rồi Sync trên máy tính. Sau đó Sync trên điện thoại.</li>
  <li><b>Không thấy nút hoặc menu của add-on:</b> tắt hẳn Anki rồi mở lại.</li>
</ul>

<h3>Mẹo để đỡ tốn lượt</h3>
<ul>
  <li>Thêm nhiều từ thì chọn <b>thẻ nhẹ</b>, về sau từ nào cần mới nâng lên thẻ đầy đủ.</li>
  <li>Từ phổ biến mà không ghi ngữ cảnh thì add-on lấy từ từ điển có sẵn, không tốn lượt nào.</li>
  <li>Thêm đầy đủ thường chỉ tốn một lượt cho mỗi từ. Vẽ hình thì dùng dịch vụ riêng nên không tính vào lượt của Gemini.</li>
</ul>
"""),
]
