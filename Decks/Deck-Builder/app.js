const SAMPLE_DECK_PATH = "deck.csv";
const MAX_DECK_SIZE = 60;
const DEFAULT_LANGUAGE = "ja";

const LANGUAGES = {
  ja: {
    htmlLang: "ja",
    csvPath: "JP_Card_Data.csv",
    locale: "ja",
    basicEnergyKind: "基本エネルギー",
    abilityPrefix: "[特性]",
    columns: {
      id: "カード ID",
      name: "カード名",
      expansion: "エキスパンションマーク",
      number: "コレクション番号",
      kind: "ポケモンの進化の段階/エネルギー・トレーナーズの種類",
      rule: "ルール",
      category: "カテゴリ",
      evolvesFrom: "進化前",
      hp: "HP",
      type: "タイプ",
      weakness: "弱点",
      resistance: "抵抗力",
      retreat: "にげる",
      attackName: "ワザ名",
      cost: "コスト",
      damage: "ダメージ",
      effect: "効果の説明",
    },
    text: {
      description: "JPカードデータから60枚のデッキを作成し、提出用のdeck.csvを書き出します。",
      languageLabel: "言語",
      languageJa: "日本語",
      languageEn: "English",
      sampleDeck: "サンプル読込",
      clearDeck: "クリア",
      searchLabel: "検索",
      searchPlaceholder: "カード名 / ID / 効果 / タイプ",
      typeLabel: "種類",
      energyLabel: "タイプ",
      allOption: "すべて",
      loading: "CSVを読み込み中です。",
      libraryAria: "カード検索",
      deckAria: "現在のデッキ",
      countLabel: "枚数",
      validationLabel: "検証",
      incomplete: "未完成",
      deckInputLabel: "deck.csv貼り付け",
      deckInputPlaceholder: "1行1カードID、またはカンマ区切りで貼り付け",
      importDeck: "貼り付け内容を反映",
      deckListTitle: "デッキリスト",
      copy: "コピー",
      copied: "コピー済",
      noEffect: "効果テキストなし",
      ability: "特性",
      effect: "効果",
      attack: "ワザ",
      countSuffix: "枚",
      addAria: (name) => `${name}を増やす`,
      removeAria: (name) => `${name}を減らす`,
      showing: (shown, total) => `${total}件中 ${shown}件を表示`,
      needMore: (count) => `あと${count}枚必要です。`,
      tooMany: (count) => `${count}枚多すぎます。`,
      ready: "60枚のdeck.csvとして出力できます。",
      missingId: (id) => `CSVに存在しないカードIDです: ${id}`,
      overFour: (name) => `${name} は同名カード合計で4枚を超えています。`,
      aceSpecTooMany: (names) => `ACE SPECはデッキに1枚までです。現在: ${names}`,
      emptyDeck: "カードがまだ選択されていません。",
      sampleLoadError: "サンプルdeck.csvを読み込めませんでした。",
      dataLoadError: "JP_Card_Data.csvを読み込めませんでした。",
      clipboardError: "クリップボードにコピーできませんでした。",
    },
  },
  en: {
    htmlLang: "en",
    csvPath: "EN_Card_Data.csv",
    locale: "en",
    basicEnergyKind: "Basic Energy",
    abilityPrefix: "[Ability]",
    columns: {
      id: "Card ID",
      name: "Card Name",
      expansion: "Expansion",
      number: "Collection No.",
      kind: "Stage (Pokémon)/Type (Energy and Trainer)",
      rule: "Rule",
      category: "Category",
      evolvesFrom: "Previous stage",
      hp: "HP",
      type: "Type",
      weakness: "Weakness",
      resistance: "Resistance (Type)",
      retreat: "Retreat",
      attackName: "Move Name",
      cost: "Cost",
      damage: "Damage",
      effect: "Effect Explanation",
    },
    text: {
      description: "Build a 60-card deck from English card data and export a submission-ready deck.csv.",
      languageLabel: "Language",
      languageJa: "日本語",
      languageEn: "English",
      sampleDeck: "Load sample",
      clearDeck: "Clear",
      searchLabel: "Search",
      searchPlaceholder: "Card name / ID / effect / type",
      typeLabel: "Kind",
      energyLabel: "Type",
      allOption: "All",
      loading: "Loading CSV.",
      libraryAria: "Card search",
      deckAria: "Current deck",
      countLabel: "Cards",
      validationLabel: "Validation",
      incomplete: "Incomplete",
      deckInputLabel: "Paste deck.csv",
      deckInputPlaceholder: "Paste one card ID per line, or comma-separated IDs",
      importDeck: "Apply pasted deck",
      deckListTitle: "Deck list",
      copy: "Copy",
      copied: "Copied",
      noEffect: "No effect text",
      ability: "Ability",
      effect: "Effect",
      attack: "Attack",
      countSuffix: "",
      addAria: (name) => `Add ${name}`,
      removeAria: (name) => `Remove ${name}`,
      showing: (shown, total) => `Showing ${shown} of ${total}`,
      needMore: (count) => `${count} more card${count === 1 ? "" : "s"} needed.`,
      tooMany: (count) => `${count} too many card${count === 1 ? "" : "s"}.`,
      ready: "Ready to export as a 60-card deck.csv.",
      missingId: (id) => `Card ID not found in the CSV: ${id}`,
      overFour: (name) => `${name} exceeds the four-card limit across cards with the same name.`,
      aceSpecTooMany: (names) => `Only one ACE SPEC card is allowed per deck. Current: ${names}`,
      emptyDeck: "No cards selected yet.",
      sampleLoadError: "Could not load the sample deck.csv.",
      dataLoadError: "Could not load EN_Card_Data.csv.",
      clipboardError: "Could not copy to the clipboard.",
    },
  },
};

const state = {
  language: localStorage.getItem("ptcgDeckLanguage") || DEFAULT_LANGUAGE,
  cards: [],
  cardById: new Map(),
  deck: new Map(),
  query: "",
  typeFilter: "",
  energyFilter: "",
};

const el = {
  searchInput: document.querySelector("#searchInput"),
  typeFilter: document.querySelector("#typeFilter"),
  energyFilter: document.querySelector("#energyFilter"),
  statusLine: document.querySelector("#statusLine"),
  cardList: document.querySelector("#cardList"),
  deckCount: document.querySelector("#deckCount"),
  deckState: document.querySelector("#deckState"),
  validationMessages: document.querySelector("#validationMessages"),
  deckList: document.querySelector("#deckList"),
  languageSelect: document.querySelector("#languageSelect"),
  appDescription: document.querySelector("#appDescription"),
  languageLabel: document.querySelector("#languageLabel"),
  searchLabel: document.querySelector("#searchLabel"),
  typeLabel: document.querySelector("#typeLabel"),
  energyLabel: document.querySelector("#energyLabel"),
  libraryPanel: document.querySelector("#libraryPanel"),
  deckPanel: document.querySelector("#deckPanel"),
  countLabel: document.querySelector("#countLabel"),
  validationLabel: document.querySelector("#validationLabel"),
  deckInputLabel: document.querySelector("#deckInputLabel"),
  deckListTitle: document.querySelector("#deckListTitle"),
  deckInput: document.querySelector("#deckInput"),
  importDeckButton: document.querySelector("#importDeckButton"),
  sampleDeckButton: document.querySelector("#sampleDeckButton"),
  clearDeckButton: document.querySelector("#clearDeckButton"),
  downloadButton: document.querySelector("#downloadButton"),
  copyButton: document.querySelector("#copyButton"),
};

function languageConfig() {
  return LANGUAGES[state.language] || LANGUAGES[DEFAULT_LANGUAGE];
}

function t() {
  return languageConfig().text;
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];

    if (char === '"') {
      if (inQuotes && next === '"') {
        field += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }

    if (char === "," && !inQuotes) {
      row.push(field);
      field = "";
      continue;
    }

    if ((char === "\n" || char === "\r") && !inQuotes) {
      if (char === "\r" && next === "\n") i += 1;
      row.push(field);
      if (row.some((value) => value !== "")) rows.push(row);
      row = [];
      field = "";
      continue;
    }

    field += char;
  }

  row.push(field);
  if (row.some((value) => value !== "")) rows.push(row);
  return rows;
}

function normalize(value) {
  return (value || "").trim();
}

function cleanValue(value) {
  const normalized = normalize(value);
  return normalized === "n/a" ? "" : normalized;
}

function toRecords(csvText) {
  const rows = parseCsv(csvText.replace(/^\uFEFF/, ""));
  const headers = rows.shift();
  return rows.map((row) => {
    const record = {};
    headers.forEach((header, index) => {
      record[header] = normalize(row[index]);
    });
    return record;
  });
}

function buildCards(records) {
  const grouped = new Map();
  const { columns } = languageConfig();

  for (const record of records) {
    const id = Number(record[columns.id]);
    if (!Number.isFinite(id)) continue;

    if (!grouped.has(id)) {
      grouped.set(id, {
        id,
        name: cleanValue(record[columns.name]),
        expansion: cleanValue(record[columns.expansion]),
        number: cleanValue(record[columns.number]),
        kind: cleanValue(record[columns.kind]),
        rule: cleanValue(record[columns.rule]),
        category: cleanValue(record[columns.category]),
        evolvesFrom: cleanValue(record[columns.evolvesFrom]),
        hp: cleanValue(record[columns.hp]),
        type: cleanValue(record[columns.type]),
        weakness: cleanValue(record[columns.weakness]),
        resistance: cleanValue(record[columns.resistance]),
        retreat: cleanValue(record[columns.retreat]),
        attacks: [],
        effects: new Set(),
      });
    }

    const card = grouped.get(id);
    const attackName = cleanValue(record[columns.attackName]);
    const effect = cleanValue(record[columns.effect]);
    if (attackName) {
      const cost = cleanValue(record[columns.cost]);
      const damage = cleanValue(record[columns.damage]);
      const abilityPrefix = languageConfig().abilityPrefix;
      const isAbility = attackName.startsWith(abilityPrefix);
      card.attacks.push({
        name: isAbility ? attackName.slice(abilityPrefix.length).trim() : attackName,
        label: getActionLabel({ isAbility, cost, damage, effect }),
        cost,
        damage,
        effect,
      });
    }
    if (effect) card.effects.add(effect);
  }

  return [...grouped.values()].map((card) => ({
    ...card,
    effects: [...card.effects],
    searchText: [
      card.id,
      card.name,
      card.expansion,
      card.number,
      card.kind,
      card.rule,
      card.category,
      card.evolvesFrom,
      card.hp,
      card.type,
      ...card.effects,
      ...card.attacks.flatMap((attack) => [attack.name, attack.cost, attack.damage, attack.effect]),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase(),
  }));
}

function getActionLabel({ isAbility, cost, damage, effect }) {
  const text = t();
  if (isAbility) return text.ability;
  if (!cost && !damage && effect) return text.effect;
  return text.attack;
}

function isBasicEnergy(card) {
  return card?.kind === languageConfig().basicEnergyKind;
}

function isAceSpec(card) {
  return card?.rule === "ACE SPEC";
}

function countByName(name) {
  let total = 0;
  for (const [id, count] of state.deck.entries()) {
    const card = state.cardById.get(id);
    if (card?.name === name) total += count;
  }
  return total;
}

function aceSpecCount() {
  let total = 0;
  for (const [id, count] of state.deck.entries()) {
    if (isAceSpec(state.cardById.get(id))) total += count;
  }
  return total;
}

function deckTotal() {
  return [...state.deck.values()].reduce((sum, count) => sum + count, 0);
}

function setCount(id, count) {
  const card = state.cardById.get(id);
  if (!card) return;

  const nextCount = Math.max(0, Math.floor(count));
  if (nextCount === 0) {
    state.deck.delete(id);
  } else {
    state.deck.set(id, nextCount);
  }
  render();
}

function addCard(id) {
  const card = state.cardById.get(id);
  const current = state.deck.get(id) || 0;
  if (!card || deckTotal() >= MAX_DECK_SIZE) return;
  if (isAceSpec(card) && aceSpecCount() >= 1) return;
  if (!isBasicEnergy(card) && countByName(card.name) >= 4) return;
  setCount(id, current + 1);
}

function removeCard(id) {
  setCount(id, (state.deck.get(id) || 0) - 1);
}

function visibleCards() {
  const query = state.query.toLowerCase();
  return state.cards
    .filter((card) => !state.typeFilter || card.kind === state.typeFilter)
    .filter((card) => !state.energyFilter || card.type === state.energyFilter)
    .filter((card) => !query || card.searchText.includes(query))
    .slice(0, 240);
}

function renderLibrary() {
  const cards = visibleCards();
  const totalMatches = state.cards
    .filter((card) => !state.typeFilter || card.kind === state.typeFilter)
    .filter((card) => !state.energyFilter || card.type === state.energyFilter)
    .filter((card) => !state.query || card.searchText.includes(state.query.toLowerCase())).length;

  el.statusLine.textContent = t().showing(cards.length, totalMatches);
  el.cardList.innerHTML = cards.map(renderCard).join("");
}

function renderCard(card) {
  const count = state.deck.get(card.id) || 0;
  const canAdd = canAddCard(card);
  return `
    <article class="card-item">
      <div class="card-top">
        <div>
          <div class="card-name">${escapeHtml(card.name)}</div>
          <div class="card-id">ID ${card.id} / ${escapeHtml(card.expansion)} ${escapeHtml(card.number)}</div>
        </div>
        <span class="chip">${count}${escapeHtml(t().countSuffix)}</span>
      </div>
      <div class="meta">
        <span class="chip">${escapeHtml(card.kind)}</span>
        ${isAceSpec(card) ? `<span class="chip ace-spec">ACE SPEC</span>` : ""}
        ${card.type ? `<span class="chip">${escapeHtml(card.type)}</span>` : ""}
        ${card.hp ? `<span class="chip">HP ${escapeHtml(card.hp)}</span>` : ""}
      </div>
      ${renderCardText(card)}
      <div class="count-controls">
        <button type="button" data-action="remove" data-id="${card.id}" aria-label="${escapeAttr(t().removeAria(card.name))}">−</button>
        <strong>${count}</strong>
        <button type="button" data-action="add" data-id="${card.id}" ${canAdd ? "" : "disabled"} aria-label="${escapeAttr(t().addAria(card.name))}">＋</button>
      </div>
    </article>
  `;
}

function canAddCard(card) {
  if (!card || deckTotal() >= MAX_DECK_SIZE) return false;
  if (isAceSpec(card) && aceSpecCount() >= 1) return false;
  return isBasicEnergy(card) || countByName(card.name) < 4;
}

function renderCardText(card) {
  if (!card.attacks.length) {
    const effect = card.effects[0];
    return `<p class="card-effect">${escapeHtml(effect || t().noEffect)}</p>`;
  }

  return `
    <div class="card-actions">
      ${card.attacks.map((attack) => `
        <div class="card-action">
          <div class="action-head">
            <span class="action-label">${escapeHtml(attack.label)}</span>
            <strong>${escapeHtml(attack.name)}</strong>
            ${attack.cost ? `<small>${escapeHtml(attack.cost)}</small>` : ""}
            ${attack.damage ? `<b>${escapeHtml(attack.damage)}</b>` : ""}
          </div>
          ${attack.effect ? `<p>${escapeHtml(attack.effect)}</p>` : ""}
        </div>
      `).join("")}
    </div>
  `;
}

function renderDeck() {
  const total = deckTotal();
  const messages = validateDeck();
  const hasErrors = messages.some((message) => message.level === "error");
  const isComplete = total === MAX_DECK_SIZE && !hasErrors;

  el.deckCount.textContent = `${total} / ${MAX_DECK_SIZE}`;
  el.deckState.textContent = isComplete ? "OK" : t().incomplete;
  el.downloadButton.disabled = !isComplete;
  el.copyButton.disabled = total === 0;
  el.validationMessages.innerHTML = messages.map((message) => `<div class="message ${message.level}">${escapeHtml(message.text)}</div>`).join("");

  const rows = [...state.deck.entries()]
    .map(([id, count]) => ({ card: state.cardById.get(id), count }))
    .filter((entry) => entry.card)
    .sort((a, b) => a.card.id - b.card.id);

  el.deckList.innerHTML = rows.length
    ? rows.map(({ card, count }) => renderDeckRow(card, count)).join("")
    : `<div class="message warn">${escapeHtml(t().emptyDeck)}</div>`;
}

function renderDeckRow(card, count) {
  const canAdd = canAddCard(card);
  return `
    <div class="deck-row">
      <strong>${count}</strong>
      <div class="deck-row-name">
        <span>${escapeHtml(card.name)}</span>
        <small>ID ${card.id} / ${escapeHtml(card.kind)}</small>
      </div>
      <div class="row-buttons">
        <button type="button" data-action="remove" data-id="${card.id}" aria-label="${escapeAttr(t().removeAria(card.name))}">−</button>
        <button type="button" data-action="add" data-id="${card.id}" ${canAdd ? "" : "disabled"} aria-label="${escapeAttr(t().addAria(card.name))}">＋</button>
      </div>
    </div>
  `;
}

function validateDeck() {
  const messages = [];
  const total = deckTotal();

  if (total < MAX_DECK_SIZE) {
    messages.push({ level: "warn", text: t().needMore(MAX_DECK_SIZE - total) });
  } else if (total > MAX_DECK_SIZE) {
    messages.push({ level: "error", text: t().tooMany(total - MAX_DECK_SIZE) });
  } else {
    messages.push({ level: "ok", text: t().ready });
  }

  const nameCounts = new Map();
  let aceSpecs = [];
  for (const [id, count] of state.deck.entries()) {
    const card = state.cardById.get(id);
    if (!card) {
      messages.push({ level: "error", text: t().missingId(id) });
      continue;
    }
    if (!isBasicEnergy(card)) {
      nameCounts.set(card.name, (nameCounts.get(card.name) || 0) + count);
    }
    if (isAceSpec(card)) {
      aceSpecs.push({ card, count });
    }
  }

  for (const [name, count] of nameCounts.entries()) {
    if (count > 4) {
      messages.push({ level: "error", text: t().overFour(name) });
    }
  }

  const totalAceSpecs = aceSpecs.reduce((sum, entry) => sum + entry.count, 0);
  if (totalAceSpecs > 1) {
    const names = aceSpecs.map((entry) => `${entry.card.name} x${entry.count}`).join(state.language === "ja" ? "、" : ", ");
    messages.push({ level: "error", text: t().aceSpecTooMany(names) });
  }

  return messages;
}

function deckCsvText() {
  const ids = [];
  for (const [id, count] of [...state.deck.entries()].sort((a, b) => a[0] - b[0])) {
    for (let i = 0; i < count; i += 1) ids.push(String(id));
  }
  return `${ids.join("\n")}\n`;
}

function downloadDeck() {
  const blob = new Blob([deckCsvText()], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "deck.csv";
  document.body.append(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function copyDeck() {
  await navigator.clipboard.writeText(deckCsvText());
  el.copyButton.textContent = t().copied;
  window.setTimeout(() => {
    el.copyButton.textContent = t().copy;
  }, 1200);
}

function importDeckText(text) {
  const ids = text
    .split(/[\s,]+/)
    .map((value) => value.trim())
    .filter(Boolean)
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value));

  state.deck.clear();
  for (const id of ids) {
    state.deck.set(id, (state.deck.get(id) || 0) + 1);
  }
  render();
}

async function loadSampleDeck() {
  const response = await fetch(SAMPLE_DECK_PATH);
  if (!response.ok) throw new Error(t().sampleLoadError);
  importDeckText(await response.text());
}

function fillFilters() {
  const kinds = uniqueSorted(state.cards.map((card) => card.kind).filter(Boolean));
  const types = uniqueSorted(state.cards.map((card) => card.type).filter(Boolean));

  el.typeFilter.innerHTML = `<option value="">${escapeHtml(t().allOption)}</option>`;
  el.energyFilter.innerHTML = `<option value="">${escapeHtml(t().allOption)}</option>`;
  el.typeFilter.insertAdjacentHTML("beforeend", kinds.map((kind) => `<option value="${escapeAttr(kind)}">${escapeHtml(kind)}</option>`).join(""));
  el.energyFilter.insertAdjacentHTML("beforeend", types.map((type) => `<option value="${escapeAttr(type)}">${escapeHtml(type)}</option>`).join(""));
}

function uniqueSorted(values) {
  return [...new Set(values)].sort((a, b) => a.localeCompare(b, languageConfig().locale));
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  })[char]);
}

function escapeAttr(value) {
  return escapeHtml(value);
}

function render() {
  renderLibrary();
  renderDeck();
}

function updateStaticText() {
  const text = t();
  document.documentElement.lang = languageConfig().htmlLang;
  el.appDescription.textContent = text.description;
  el.languageLabel.textContent = text.languageLabel;
  el.languageSelect.options[0].textContent = text.languageJa;
  el.languageSelect.options[1].textContent = text.languageEn;
  el.sampleDeckButton.textContent = text.sampleDeck;
  el.clearDeckButton.textContent = text.clearDeck;
  el.searchLabel.textContent = text.searchLabel;
  el.searchInput.placeholder = text.searchPlaceholder;
  el.typeLabel.textContent = text.typeLabel;
  el.energyLabel.textContent = text.energyLabel;
  el.statusLine.textContent = text.loading;
  el.libraryPanel.setAttribute("aria-label", text.libraryAria);
  el.deckPanel.setAttribute("aria-label", text.deckAria);
  el.countLabel.textContent = text.countLabel;
  el.validationLabel.textContent = text.validationLabel;
  el.deckInputLabel.textContent = text.deckInputLabel;
  el.deckInput.placeholder = text.deckInputPlaceholder;
  el.importDeckButton.textContent = text.importDeck;
  el.deckListTitle.textContent = text.deckListTitle;
  el.copyButton.textContent = text.copy;
}

async function loadCardData() {
  updateStaticText();
  el.cardList.innerHTML = "";
  const response = await fetch(languageConfig().csvPath);
  if (!response.ok) throw new Error(t().dataLoadError);
  const records = toRecords(await response.text());
  state.cards = buildCards(records);
  state.cardById = new Map(state.cards.map((card) => [card.id, card]));
  state.typeFilter = "";
  state.energyFilter = "";
  el.typeFilter.value = "";
  el.energyFilter.value = "";
  fillFilters();
  render();
}

async function setLanguage(language) {
  if (!LANGUAGES[language] || language === state.language) return;
  state.language = language;
  localStorage.setItem("ptcgDeckLanguage", language);
  el.languageSelect.value = language;
  await loadCardData();
}

function bindEvents() {
  el.searchInput.addEventListener("input", () => {
    state.query = el.searchInput.value.trim();
    renderLibrary();
  });

  el.typeFilter.addEventListener("change", () => {
    state.typeFilter = el.typeFilter.value;
    renderLibrary();
  });

  el.energyFilter.addEventListener("change", () => {
    state.energyFilter = el.energyFilter.value;
    renderLibrary();
  });

  document.body.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const id = Number(button.dataset.id);
    if (button.dataset.action === "add") addCard(id);
    if (button.dataset.action === "remove") removeCard(id);
  });

  el.importDeckButton.addEventListener("click", () => importDeckText(el.deckInput.value));
  el.sampleDeckButton.addEventListener("click", () => loadSampleDeck().catch((error) => alert(error.message)));
  el.clearDeckButton.addEventListener("click", () => {
    state.deck.clear();
    render();
  });
  el.downloadButton.addEventListener("click", downloadDeck);
  el.copyButton.addEventListener("click", () => copyDeck().catch(() => alert(t().clipboardError)));
  el.languageSelect.addEventListener("change", () => {
    setLanguage(el.languageSelect.value).catch((error) => {
      el.statusLine.textContent = error.message;
      el.validationMessages.innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
    });
  });
}

async function init() {
  if (!LANGUAGES[state.language]) state.language = DEFAULT_LANGUAGE;
  el.languageSelect.value = state.language;
  bindEvents();
  await loadCardData();
}

init().catch((error) => {
  el.statusLine.textContent = error.message;
  el.validationMessages.innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
});
