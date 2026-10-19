// Локал TinyMCE (интернет талаб қилинмайди).
// mode: 'candidate' — номзод жавоби (расм ва ҳаволасиз), 'author' — савол тузувчи (тўлиқ).
const EDITOR_PRESETS = {
  candidate: {
    plugins: 'lists advlist table charmap fullscreen wordcount searchreplace autoresize',
    toolbar: 'undo redo | blocks | bold italic underline strikethrough | superscript subscript | ' +
             'bullist numlist outdent indent | alignleft aligncenter alignright | table | charmap hr | ' +
             'searchreplace removeformat | fullscreen',
    block_formats: 'Оддий матн=p; Сарлавҳа=h3; Кичик сарлавҳа=h4; Псевдокод / ҳисоб=pre',
    min_height: 360,
    max_height: 900,
    autoresize_bottom_margin: 30,
  },
  author: {
    plugins: 'lists advlist table charmap fullscreen wordcount searchreplace image code autoresize',
    toolbar: 'undo redo | blocks | bold italic underline strikethrough | forecolor backcolor | ' +
             'superscript subscript | alignleft aligncenter alignright alignjustify | ' +
             'bullist numlist outdent indent | table image charmap hr | searchreplace removeformat code | fullscreen',
    block_formats: 'Оддий матн=p; Сарлавҳа=h3; Кичик сарлавҳа=h4; Псевдокод / ҳисоб=pre; Иқтибос=blockquote',
    min_height: 260,
    max_height: 700,
    image_title: false,
    image_description: true,
    image_dimensions: true,
    automatic_uploads: true,
    file_picker_types: 'image',
    images_file_types: 'png,jpg,jpeg,gif,webp',
    images_upload_handler: (blobInfo, progress) => new Promise((resolve, reject) => {
      const data = new FormData();
      data.append('file', blobInfo.blob(), blobInfo.filename());
      const csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
      fetch('/staff/upload-image/', {method: 'POST', body: data, headers: {'X-CSRFToken': csrf}, credentials: 'same-origin'})
        .then(r => r.json().then(j => ({ok: r.ok, j})))
        .then(({ok, j}) => ok && j.location ? resolve(j.location) : reject(j.error || 'Юклаб бўлмади'))
        .catch(() => reject('Юклаб бўлмади'));
    }),
    color_map: ['000000', 'Қора', '1d4ed8', 'Кўк', 'b91c1c', 'Қизил', '15803d', 'Яшил', 'b45309', 'Тўқ сариқ',
                '64748b', 'Кулранг', 'fff3bf', 'Сариқ фон', 'dbeafe', 'Кўк фон', 'dcfce7', 'Яшил фон', 'fee2e2', 'Қизил фон'],
    custom_colors: false,
  },
};

function initEditor(selector, extra, mode) {
  const preset = EDITOR_PRESETS[mode || 'candidate'];
  const ru = window.EXAM && window.EXAM.lang === 'ru';   // рус тилидаги тест
  return tinymce.init(Object.assign({
    selector: selector,
    license_key: 'gpl',
    language: ru ? 'ru' : 'uz_cyrl',
    language_url: ru ? undefined : '/static/exam/tinymce-uz-cyrl.js',
    menubar: false,
    branding: false,
    promotion: false,
    statusbar: true,
    elementpath: false,
    toolbar_mode: 'wrap',
    paste_data_images: false,
    contextmenu: false,
    browser_spellcheck: false,
    convert_urls: false,
    table_default_styles: {'border-collapse': 'collapse', 'width': '100%'},
    table_default_attributes: {border: '1'},
    content_style: 'body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;font-size:16px;line-height:1.6;color:#0f172a;margin:14px}' +
                   'table{border-collapse:collapse}td,th{border:1px solid #cbd5e1;padding:6px 10px}' +
                   'pre{background:#f1f5f9;padding:10px 12px;border-radius:6px;font-size:14px;white-space:pre-wrap}' +
                   'img{max-width:100%;height:auto}blockquote{border-left:3px solid #cbd5e1;margin:0;padding-left:12px;color:#475569}',
  }, preset, ru ? {block_formats: 'Обычный текст=p; Заголовок=h3; Подзаголовок=h4; Псевдокод / расчет=pre'} : {},
  extra || {}));
}
