import {effectiveStyle, normalizeHex} from './style-model.mjs';

function node(tag, text = '', className = '') {
  const result = document.createElement(tag); result.textContent = text; result.className = className; return result;
}

export function mountStyleEditor(host, initial, config, onChange, onValidity) {
  const style = effectiveStyle(initial, config), invalid = new Set();
  host.replaceChildren();
  const error = node('p', '', 'style-error'); error.setAttribute('role', 'alert');
  const changed = () => onChange(structuredClone(style));
  function validity(input, message) {
    input.setCustomValidity(message); input.setAttribute('aria-invalid', String(Boolean(message)));
    if (message) invalid.add(input); else invalid.delete(input);
    error.textContent = invalid.size ? '请修正标红的颜色或数值；无效输入不会保存。' : '';
    onValidity(invalid.size === 0);
  }

  const tabs = node('div', '', 'style-tabs'), colors = node('section'), layout = node('section');
  colors.id = 'theme-fields'; layout.id = 'layout-fields'; layout.hidden = true;
  for (const [text, panel] of [['主题颜色', colors], ['版式参数', layout]]) {
    const tab = node('button', text); tab.type = 'button'; tab.setAttribute('aria-controls', panel.id);
    tab.setAttribute('aria-pressed', String(panel === colors));
    tab.addEventListener('click', () => {
      colors.hidden = panel !== colors; layout.hidden = panel !== layout;
      for (const item of tabs.children) item.setAttribute('aria-pressed', String(item === tab));
    }); tabs.append(tab);
  }

  const sample = node('div', '', 'theme-sample'), title = node('strong', '教育背景'), rule = node('div', '', 'theme-rule');
  sample.append(title, rule, node('p', '标题与分隔线使用主题色，正文保持黑色。'));
  colors.append(sample);
  const swatches = [];
  const hexLabel = node('label', '', 'field'), hex = node('input');
  hexLabel.append(node('span', 'HEX 颜色'), hex); hex.type = 'text'; hex.maxLength = 7; hex.spellcheck = false;
  hex.placeholder = '#2457A7'; hex.value = style.theme_color;
  const pickerLabel = node('label', '', 'field'), picker = node('input');
  pickerLabel.append(node('span', '调色盘取色'), picker); picker.type = 'color'; picker.value = style.theme_color;
  const sync = () => {
    title.style.color = rule.style.backgroundColor = style.theme_color;
    hex.value = picker.value = style.theme_color;
    for (const [swatch, color] of swatches) swatch.setAttribute('aria-pressed', String(color === style.theme_color.toUpperCase()));
    validity(hex, '');
  };
  const choose = (color) => { style.theme_color = color; sync(); changed(); };
  for (const palette of config.palettes) {
    const group = node('div', '', 'palette-group'); group.setAttribute('role', 'group'); group.setAttribute('aria-label', palette.name);
    group.append(node('span', palette.name));
    const options = node('div', '', 'palette-swatches');
    for (const color of palette.colors) {
      const swatch = node('button', '', 'color-swatch'); swatch.type = 'button'; swatch.style.backgroundColor = color;
      swatch.setAttribute('aria-label', `${palette.name} ${color}`); swatch.title = color;
      swatch.addEventListener('click', () => choose(color)); swatches.push([swatch, color]); options.append(swatch);
    }
    group.append(options); colors.append(group);
  }
  const custom = node('div', '', 'custom-color'); custom.append(hexLabel, pickerLabel); colors.append(custom);
  hex.addEventListener('input', () => {
    const value = normalizeHex(hex.value); validity(hex, value ? '' : '请输入六位 HEX 颜色，如 #2457A7');
    if (value) choose(value);
  });
  picker.addEventListener('input', () => choose(picker.value.toUpperCase()));

  const addSelect = (label, key) => {
    const row = node('label', '', 'field style-field'), select = node('select'); row.append(node('span', label), select);
    for (const value of config.sizes[key]) {
      const option = node('option', `${value}px`); option.value = String(value); select.append(option);
    }
    select.value = String(style[key]); select.addEventListener('change', () => { style[key] = Number(select.value); changed(); });
    layout.append(row);
  };
  const number = (label, object, key, min, max, step = 1) => {
    const row = node('label', '', 'field style-field'), input = node('input'); row.append(node('span', label), input);
    input.type = 'number'; input.min = min; input.max = max; input.step = step; input.required = true; input.value = String(object[key]);
    input.addEventListener('input', () => {
      input.setCustomValidity('');
      const value = input.valueAsNumber, valid = input.validity.valid && Number.isFinite(value) && (step !== 1 || Number.isInteger(value));
      validity(input, valid ? '' : `请输入 ${min} 至 ${max} 的${step === 1 ? '整数' : '数值'}`);
      if (valid) { object[key] = value; changed(); }
    }); return row;
  };
  addSelect('模块标题大小', 'section_title_size_px'); addSelect('模块内容大小', 'content_size_px'); addSelect('姓名大小', 'name_size_px');
  layout.append(number('模块间距 (px)', style, 'section_gap_px', 0, 40));
  const rhythm = config.rhythm;
  layout.append(node('p', `固定留白：正文行高 ${rhythm.body_line_height} 倍，顶部信息行额外 ${rhythm.header_line_gap_px}px，列表项 ${rhythm.list_item_gap_px}px，段落 ${rhythm.paragraph_gap_px}px，同模块条目 ${rhythm.entry_gap_px}px。无需逐项调整。`, 'fixed-rhythm-note'));
  const margins = node('fieldset', '', 'style-margins'); margins.append(node('legend', '页边距 (px)'));
  for (const [key, label] of [['top', '上'], ['bottom', '下'], ['left', '左'], ['right', '右']]) margins.append(number(label, style.margins_px, key, 0, 120));
  layout.append(margins, node('p', '模块间距可单独调整；其余行文留白由模板统一控制。px 按 96 px/英寸换算到 PDF，不随预览缩放改变。', 'field-hint'));
  host.append(tabs, colors, layout, error); sync();
}
