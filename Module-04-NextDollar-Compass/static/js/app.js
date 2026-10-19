/*
  app.js - the page's behavior.
  Course: ITAI 2372 - Module 04 (AI in Finance) | Project: NextDollar Compass

  The browser keeps everything you type in one `state` object (nothing is
  saved on a server). Buttons call the Flask API with fetch():
    POST /api/extract     read a pay stub or statement
    POST /api/categorize  sort expenses with the ML model (+ Gemini)
    POST /api/plan        calculate the plan and explain it
    POST /api/ask         answer a question about the plan
*/
(function () {
  "use strict";
  const { money, esc } = window.Charts;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const PERIODS = { weekly: 52, biweekly: 26, semimonthly: 24, monthly: 12, quarterly: 4, yearly: 1 };
  const FREQ_LABEL = { weekly: "weekly", biweekly: "every 2 weeks", semimonthly: "twice a month", monthly: "monthly", quarterly: "every 3 months", yearly: "yearly", csv: "from bank file" };
  const num = v => { const x = parseFloat(String(v ?? "").replace(/[$,\s]/g, "")); return isFinite(x) ? x : 0; };
  const toMonthly = (a, f) => num(a) * (PERIODS[f] || 12) / 12;
  let nextId = 1;
  const uid = () => "i" + (nextId++);

  const DEBT_KIND = { credit_card: "Credit card", car: "Car loan", mortgage: "Mortgage", student: "Student loan", personal: "Personal loan", other: "Other loan" };
  const GOALS = [
    { type: "emergency_fund", title: "Build an emergency fund", desc: "Cash for surprise bills or a lost job." },
    { type: "pay_off_cards", title: "Pay off credit cards", desc: "Also student and personal loans." },
    { type: "pay_off_car", title: "Pay off my car early", desc: "Extra payments toward the car loan." },
    { type: "pay_off_mortgage", title: "Pay off my mortgage early", desc: "Extra principal each month." },
    { type: "save_for_purchase", title: "Save for something", desc: "A car, a trip, a down payment..." },
    { type: "invest", title: "Invest for the long term", desc: "Stocks, ETFs or crypto, filtered by your values." },
  ];
  const WEIGHTS = { 1: [1], 2: [.6, .4], 3: [.5, .3, .2], 4: [.4, .3, .2, .1], 5: [.35, .25, .2, .12, .08], 6: [.3, .25, .18, .12, .1, .05] };
  const QUICK = [["Rent", 0], ["Groceries", 0], ["Electric bill", 0], ["Phone bill", 0], ["Internet", 0], ["Car insurance", 0], ["Gas for car", 0], ["Eating out", 0], ["Streaming", 0], ["Gym membership", 0]];

  let SUBS = {};            // subcategory -> {category, type}
  let TAXONOMY = [];
  let lastPlan = null;

  const state = {
    income: { paychecks: [{ id: uid(), label: "Main job", frequency: "biweekly", gross: "", net: "" }], other: [] },
    current_savings: "",
    expenses: [],
    debts: [],
    goals: [],
    debt_method: "avalanche",
    spending_cut_pct: 0,
    investing: { assets: ["etfs"], risk: "moderate", horizon_years: 10, screen: "none", custom_values: "", choices: {} },
    chat: [],
  };

  // ---------------------------------------------------------------- helpers
  async function api(path, body, isForm = false) {
    const opts = { method: body ? "POST" : "GET" };
    if (body) {
      if (isForm) opts.body = body;
      else { opts.body = JSON.stringify(body); opts.headers = { "Content-Type": "application/json" }; }
    }
    const res = await fetch(path, opts);
    const data = await res.json().catch(() => ({ error: "The server sent an unreadable reply." }));
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status}).`);
    return data;
  }
  function toast(text) {
    const t = $("#toast");
    t.textContent = text;
    t.classList.add("show");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => t.classList.remove("show"), 3800);
  }
  function setMsg(key, text, isErr = false) {
    const el = $(`#msg-${key}`);
    if (!el) return;
    el.textContent = text || "";
    el.classList.toggle("err", !!isErr);
  }
  const typeColor = t => ({ need: css("--need"), want: css("--want"), giving: css("--give"), debt: css("--debt"), savings: css("--save"), other: css("--want") }[t] || css("--ink-3"));

  // ---------------------------------------------------------------- steps
  function go(step) {
    step = Number(step);
    $$(".panel").forEach(p => (p.hidden = Number(p.dataset.panel) !== step));
    $$(".step-btn").forEach(b => {
      const s = Number(b.dataset.step);
      b.classList.toggle("active", s === step);
      if (s === step) b.setAttribute("aria-current", "step"); else b.removeAttribute("aria-current");
    });
    markDone();
    if (step === 4) renderGoals();
    if (step === 5) buildPlan(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  function markDone() {
    const done = {
      1: incomeMonthly() > 0, 2: state.expenses.length > 0, 3: state.debts.length > 0, 4: state.goals.length > 0, 5: !!lastPlan,
    };
    $$(".step-btn").forEach(b => b.classList.toggle("done", !!done[b.dataset.step] && !b.classList.contains("active")));
  }

  // ---------------------------------------------------------------- the stub (live summary)
  function incomeMonthly() {
    return state.income.paychecks.reduce((s, p) => s + toMonthly(p.net, p.frequency), 0)
      + state.income.other.reduce((s, o) => s + toMonthly(o.amount, o.frequency), 0);
  }
  function liveNumbers() {
    const net = incomeMonthly();
    const byType = { need: 0, want: 0, giving: 0 };
    const hasDebts = state.debts.length > 0;
    state.expenses.forEach(e => {
      const m = e.monthly_amount ?? toMonthly(e.amount, e.frequency);
      let t = e.type || "want";
      if (t === "savings" || (t === "debt" && hasDebts)) return;
      if (t === "other") t = "want";
      if (t === "debt") t = "need";
      const cut = t === "want" ? (1 - state.spending_cut_pct / 100) : 1;
      byType[t] = (byType[t] || 0) + m * cut;
    });
    const debt = state.debts.reduce((s, d) => s + num(d.min_payment), 0);
    const spend = byType.need + byType.want + byType.giving;
    return { net, byType, debt, free: net - spend - debt };
  }
  function renderStub() {
    const n = liveNumbers();
    $("#stubIncome").textContent = money(n.net);
    const segs = [
      { label: "Needs", value: n.byType.need, color: css("--need") },
      { label: "Debt payments", value: n.debt, color: css("--debt") },
      { label: "Wants", value: n.byType.want, color: css("--want") },
      { label: "Giving", value: n.byType.giving, color: css("--give") },
      { label: "Free for goals", value: Math.max(0, n.free), color: css("--free") },
    ];
    const total = segs.reduce((s, x) => s + x.value, 0);
    $("#stubSplit").innerHTML = total > 0
      ? segs.filter(s => s.value > 0).map(s => `<span style="flex:${s.value} 1 0;background:${s.color}" title="${s.label}: ${money(s.value)}"></span>`).join("")
      : "";
    $("#stubLines").innerHTML = segs.map(s => `<dt><i style="background:${s.color}"></i>${s.label}</dt><dd>${money(s.value)}</dd>`).join("");
    const memo = $("#stubMemo");
    memo.classList.remove("bad");
    if (n.net <= 0) memo.textContent = "Add your pay to start.";
    else if (n.free < 0) { memo.textContent = `Over budget by ${money(-n.free)} a month.`; memo.classList.add("bad"); }
    else memo.textContent = `Memo: ${money(n.free)} a month is free for your goals.`;
    markDone();
  }

  // ---------------------------------------------------------------- step 1: income
  function freqSelect(value, attrs) {
    const opts = ["weekly", "biweekly", "semimonthly", "monthly"].map(f => `<option value="${f}" ${f === value ? "selected" : ""}>${FREQ_LABEL[f][0].toUpperCase() + FREQ_LABEL[f].slice(1)}</option>`).join("");
    return `<select ${attrs}>${opts}</select>`;
  }
  function renderIncome() {
    $("#paychecks").innerHTML = state.income.paychecks.map((p, i) => `
      <div class="row" data-pay="${p.id}">
        <div class="field"><label for="pl-${p.id}">Job</label><input id="pl-${p.id}" data-k="label" value="${esc(p.label)}"></div>
        <div class="field"><label for="pf-${p.id}">Paid</label>${freqSelect(p.frequency, `id="pf-${p.id}" data-k="frequency"`)}</div>
        <div class="field"><label for="pg-${p.id}">Gross per check</label><input id="pg-${p.id}" data-k="gross" inputmode="decimal" placeholder="before taxes" value="${esc(p.gross)}"></div>
        <div class="field"><label for="pn-${p.id}">Take-home per check</label><input id="pn-${p.id}" data-k="net" inputmode="decimal" placeholder="what lands in the bank" value="${esc(p.net)}"></div>
        <button type="button" class="icon-btn" data-del-pay="${p.id}" aria-label="Remove ${esc(p.label)}" ${state.income.paychecks.length < 2 ? "hidden" : ""}>&times;</button>
        <p class="calc">${num(p.net) ? `About ${money(toMonthly(p.net, p.frequency))} a month take-home` : ""}</p>
      </div>`).join("");
    $("#otherIncome").innerHTML = state.income.other.map(o => `
      <div class="row other" data-other="${o.id}">
        <div class="field"><label for="ol-${o.id}">Source</label><input id="ol-${o.id}" data-k="label" value="${esc(o.label)}"></div>
        <div class="field"><label for="oa-${o.id}">Amount</label><input id="oa-${o.id}" data-k="amount" inputmode="decimal" value="${esc(o.amount)}"></div>
        <div class="field"><label for="of-${o.id}">How often</label>${freqSelect(o.frequency, `id="of-${o.id}" data-k="frequency"`)}</div>
        <button type="button" class="icon-btn" data-del-other="${o.id}" aria-label="Remove ${esc(o.label)}">&times;</button>
      </div>`).join("");
    $("#currentSavings").value = state.current_savings;
    renderStub();
  }
  function bindIncome() {
    $("#paychecks").addEventListener("input", e => {
      const row = e.target.closest("[data-pay]");
      if (!row) return;
      const p = state.income.paychecks.find(x => x.id === row.dataset.pay);
      p[e.target.dataset.k] = e.target.value;
      $(".calc", row).textContent = num(p.net) ? `About ${money(toMonthly(p.net, p.frequency))} a month take-home` : "";
      renderStub();
    });
    $("#paychecks").addEventListener("click", e => {
      const id = e.target.dataset.delPay;
      if (!id) return;
      state.income.paychecks = state.income.paychecks.filter(p => p.id !== id);
      renderIncome();
    });
    $("#otherIncome").addEventListener("input", e => {
      const row = e.target.closest("[data-other]");
      if (!row) return;
      state.income.other.find(x => x.id === row.dataset.other)[e.target.dataset.k] = e.target.value;
      renderStub();
    });
    $("#otherIncome").addEventListener("click", e => {
      const id = e.target.dataset.delOther;
      if (!id) return;
      state.income.other = state.income.other.filter(o => o.id !== id);
      renderIncome();
    });
    $("#addPaycheck").addEventListener("click", () => {
      state.income.paychecks.push({ id: uid(), label: "Second job", frequency: "biweekly", gross: "", net: "" });
      renderIncome();
    });
    $("#addOther").addEventListener("click", () => {
      state.income.other.push({ id: uid(), label: "Side income", amount: "", frequency: "monthly" });
      renderIncome();
    });
    $("#currentSavings").addEventListener("input", e => { state.current_savings = e.target.value; });
  }

  // ---------------------------------------------------------------- uploads
  async function handleUpload(kind, file) {
    if (!file) return;
    const zone = $(`.drop[data-doc="${kind}"]`);
    zone.classList.add("busy");
    const msgKey = ["credit_card", "car_loan", "mortgage"].includes(kind) ? "debts" : kind;
    setMsg(msgKey, `Reading ${file.name}...`);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (kind === "bank_csv") {
        const r = await api("/api/categorize", fd, true);
        r.items.forEach(it => state.expenses.push({ id: uid(), ...it }));
        renderExpenses();
        setMsg(msgKey, `Added ${r.items.length} purchases covering about ${r.months_covered} month(s); amounts are monthly averages. ${r.skipped_deposits ? r.skipped_deposits + " deposit(s) skipped." : ""}`);
        return;
      }
      fd.append("doc_type", kind);
      const r = await api("/api/extract", fd, true);
      const f = r.fields || {};
      if (kind === "paystub") applyPaystub(f);
      else applyStatement(kind, f, file.name);
      setMsg(msgKey, r.message || "Done. Please check the numbers.");
    } catch (err) {
      setMsg(msgKey, err.message, true);
    } finally {
      zone.classList.remove("busy");
      zone.querySelector("input").value = "";
    }
  }
  function applyPaystub(f) {
    const p = state.income.paychecks[0];
    if (f.pay_frequency && PERIODS[f.pay_frequency]) p.frequency = f.pay_frequency;
    if (f.gross_pay) p.gross = f.gross_pay;
    if (f.net_pay) p.net = f.net_pay;
    renderIncome();
    const ded = (f.deductions || []).filter(d => d.amount);
    const box = $("#msg-paystub");
    if (ded.length) {
      let el = $("#deductions");
      if (!el) { el = document.createElement("div"); el.id = "deductions"; el.className = "deductions"; box.after(el); }
      el.innerHTML = ded.map(d => `<span>${esc(d.name)} ${money(d.amount)}</span>`).join("");
    }
  }
  function applyStatement(kind, f, filename) {
    const d = newDebt(kind === "credit_card" ? "credit_card" : kind === "car_loan" ? "car" : "mortgage");
    d.name = f.card_name || f.lender_name || d.name;
    d.balance = f.balance ?? "";
    d.apr = f.purchase_apr ?? f.interest_rate ?? "";
    d.min_payment = f.minimum_payment ?? f.monthly_payment ?? "";
    d.credit_limit = f.credit_limit ?? "";
    d.escrow = f.escrow ?? "";
    d.remaining_months = f.remaining_months ?? "";
    d.annual_fee = f.annual_fee ?? "";
    d.penalty_apr = f.penalty_apr ?? "";
    if (f.promo_apr !== null && f.promo_apr !== undefined) d.note = `Promo APR ${f.promo_apr}%${f.promo_ends ? " until " + f.promo_ends : ""} - the plan uses the regular APR.`;
    state.debts.push(d);
    renderDebts();
  }
  function bindUploads() {
    $$(".drop").forEach(zone => {
      const input = zone.querySelector("input");
      input.addEventListener("change", () => handleUpload(zone.dataset.doc, input.files[0]));
      zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("drag"); });
      zone.addEventListener("dragleave", () => zone.classList.remove("drag"));
      zone.addEventListener("drop", e => {
        e.preventDefault();
        zone.classList.remove("drag");
        handleUpload(zone.dataset.doc, e.dataTransfer.files[0]);
      });
    });
  }

  // ---------------------------------------------------------------- step 2: spending
  function categorySelect(e) {
    const groups = TAXONOMY.map(g => `<optgroup label="${esc(g.category)}">${g.subcategories.map(s => `<option value="${esc(s.name)}" ${s.name === e.subcategory ? "selected" : ""}>${esc(s.name)}</option>`).join("")}</optgroup>`).join("");
    return `<select data-cat="${e.id}" aria-label="Category for ${esc(e.description)}"><option value="">Not sorted yet</option>${groups}</select>`;
  }
  function badge(e) {
    if (e.method === "you") return `<span class="badge you">You</span>`;
    if (e.method === "ml") return `<span class="badge ml" title="Machine-learning model">Model ${Math.round(e.confidence * 100)}%</span>`;
    if (e.method === "gemini") return `<span class="badge gemini" title="The model was unsure; Gemini picked this">Gemini</span>`;
    if (e.method === "check") return `<span class="badge check" title="Low confidence - please check">Check</span>`;
    return `<span class="badge none">-</span>`;
  }
  function renderExpenses() {
    const rows = state.expenses.map(e => {
      const m = e.monthly_amount ?? toMonthly(e.amount, e.frequency);
      return `<tr>
        <td><span class="desc">${esc(e.description)}</span><br><span class="sub">${money(e.amount)} ${FREQ_LABEL[e.frequency] || ""}</span></td>
        <td class="num">${money(m)}</td>
        <td><span class="type-dot" style="background:${typeColor(e.type)}"></span>${categorySelect(e)}</td>
        <td>${badge(e)}</td>
        <td><button type="button" class="icon-btn" data-del-exp="${e.id}" aria-label="Remove ${esc(e.description)}">&times;</button></td>
      </tr>`;
    }).join("");
    $("#expenseRows").innerHTML = rows;
    $("#expenseEmpty").hidden = state.expenses.length > 0;
    // category bars
    const byCat = {};
    const hasDebts = state.debts.length > 0;
    state.expenses.forEach(e => {
      if (!e.subcategory || e.type === "savings" || (e.type === "debt" && hasDebts)) return;
      const c = byCat[e.category] || (byCat[e.category] = { value: 0, types: {} });
      const m = e.monthly_amount ?? toMonthly(e.amount, e.frequency);
      c.value += m;
      c.types[e.type] = (c.types[e.type] || 0) + m;
    });
    const rowsBar = Object.entries(byCat).sort((a, b) => b[1].value - a[1].value).map(([label, c]) => {
      const main = Object.entries(c.types).sort((a, b) => b[1] - a[1])[0][0];
      return { label, value: c.value, color: typeColor(main) };
    });
    window.Charts.bars($("#spendBars"), rowsBar);
    renderStub();
  }
  async function sortExpenses(onlyIds) {
    const todo = state.expenses.filter(e => e.method !== "you" && (!onlyIds || onlyIds.includes(e.id)));
    if (!todo.length) return;
    const btn = $("#sortExpenses");
    btn.disabled = true;
    try {
      const r = await api("/api/categorize", { items: todo.map(e => ({ description: e.description, amount: e.amount, frequency: e.frequency, monthly_amount: e.frequency === "csv" ? e.monthly_amount : undefined })) });
      r.items.forEach((it, i) => Object.assign(todo[i], {
        category: it.category, subcategory: it.subcategory, type: it.type, confidence: it.confidence,
        method: it.method, monthly_amount: it.monthly_amount,
      }));
      renderExpenses();
      if (!onlyIds) toast(`Sorted ${r.items.length}: ${r.counts.ml} by the model, ${r.counts.gemini} by Gemini, ${r.counts.check} to check.`);
    } catch (err) {
      toast(err.message);
    } finally {
      btn.disabled = false;
    }
  }
  function bindExpenses() {
    $("#quickAdd").innerHTML = QUICK.map(([name]) => `<button type="button" class="chip" data-quick="${name}">${name}</button>`).join("");
    $("#quickAdd").addEventListener("click", e => {
      const q = e.target.dataset.quick;
      if (!q) return;
      $("#expDesc").value = q;
      $("#expAmt").focus();
    });
    const add = () => {
      const description = $("#expDesc").value.trim();
      const amount = num($("#expAmt").value);
      if (!description || amount <= 0) { toast("Type what the expense is and an amount."); return; }
      const e = { id: uid(), description, amount, frequency: $("#expFreq").value };
      state.expenses.push(e);
      $("#expDesc").value = ""; $("#expAmt").value = "";
      $("#expDesc").focus();
      renderExpenses();
      sortExpenses([e.id]);
    };
    $("#addExpense").addEventListener("click", add);
    [$("#expDesc"), $("#expAmt")].forEach(el => el.addEventListener("keydown", e => { if (e.key === "Enter") add(); }));
    $("#sortExpenses").addEventListener("click", () => sortExpenses());
    $("#expenseRows").addEventListener("change", e => {
      const id = e.target.dataset.cat;
      if (!id) return;
      const ex = state.expenses.find(x => x.id === id);
      const sub = e.target.value;
      Object.assign(ex, sub ? { subcategory: sub, ...SUBS[sub], method: "you" } : { subcategory: null, category: null, type: null, method: null });
      renderExpenses();
    });
    $("#expenseRows").addEventListener("click", e => {
      const id = e.target.dataset.delExp;
      if (!id) return;
      state.expenses = state.expenses.filter(x => x.id !== id);
      renderExpenses();
    });
  }

  // ---------------------------------------------------------------- step 3: debts
  function newDebt(kind) {
    return { id: uid(), kind, name: DEBT_KIND[kind], balance: "", apr: "", min_payment: "", credit_limit: "", escrow: "", remaining_months: "" };
  }
  function debtField(d, key, label, hint) {
    return `<div class="field"><label for="${key}-${d.id}">${label}</label><input id="${key}-${d.id}" data-k="${key}" inputmode="decimal" placeholder="${hint || ""}" value="${esc(d[key] ?? "")}"></div>`;
  }
  function debtCalc(d) {
    const bal = num(d.balance), apr = num(d.apr), pay = num(d.min_payment) - (d.kind === "mortgage" ? num(d.escrow) : 0);
    if (!bal || !apr) return "";
    const interest = bal * apr / 1200;
    let txt = `Interest this month: <b>${money(interest)}</b>.`;
    if (pay > 0 && pay <= interest) txt += " Your payment does not cover the interest, so the balance grows.";
    else if (pay > 0) txt += ` ${Math.round(100 * interest / pay)}% of your payment goes to interest.`;
    if (d.kind === "credit_card" && num(d.credit_limit)) txt += ` Using ${Math.round(100 * bal / num(d.credit_limit))}% of the limit.`;
    return txt;
  }
  function renderDebts() {
    $("#debtList").innerHTML = state.debts.map(d => {
      const payLabel = d.kind === "credit_card" ? "Minimum payment" : d.kind === "mortgage" ? "Monthly payment (with escrow)" : "Monthly payment";
      let extra = "";
      if (d.kind === "credit_card") extra = debtField(d, "credit_limit", "Credit limit", "optional");
      else if (d.kind === "mortgage") extra = debtField(d, "escrow", "Escrow part", "taxes + insurance") + debtField(d, "remaining_months", "Months left", "optional");
      else extra = debtField(d, "remaining_months", "Months left", "optional");
      return `<div class="debt" data-debt="${d.id}">
        <div class="debt-head"><input data-k="name" aria-label="Debt name" value="${esc(d.name)}"><span class="kind">${DEBT_KIND[d.kind]}</span>
          <button type="button" class="icon-btn" data-del-debt="${d.id}" aria-label="Remove ${esc(d.name)}">&times;</button></div>
        <div class="debt-fields">${debtField(d, "balance", "Balance owed", "$")}${debtField(d, "apr", "Interest rate (APR %)", "e.g. 24.99")}${debtField(d, "min_payment", payLabel, d.kind === "credit_card" ? "blank = estimate" : "$")}${extra}</div>
        <p class="debt-calc">${debtCalc(d)}</p>
        ${d.note ? `<p class="hint">${esc(d.note)}</p>` : ""}
      </div>`;
    }).join("");
    renderStub();
  }
  function bindDebts() {
    $(".add-debt").addEventListener("click", e => {
      const k = e.target.dataset.addDebt;
      if (!k) return;
      state.debts.push(newDebt(k));
      renderDebts();
      const inputs = $$(`[data-debt] input[data-k="balance"]`);
      inputs[inputs.length - 1]?.focus();
    });
    $("#debtList").addEventListener("input", e => {
      const card = e.target.closest("[data-debt]");
      if (!card) return;
      const d = state.debts.find(x => x.id === card.dataset.debt);
      d[e.target.dataset.k] = e.target.value;
      $(".debt-calc", card).innerHTML = debtCalc(d);
      renderStub();
    });
    $("#debtList").addEventListener("click", e => {
      const id = e.target.dataset.delDebt;
      if (!id) return;
      state.debts = state.debts.filter(d => d.id !== id);
      renderDebts();
    });
    $$('input[name="method"]').forEach(r => r.addEventListener("change", () => { state.debt_method = r.value; }));
  }

  // ---------------------------------------------------------------- step 4: goals
  function renderGoals() {
    const chosen = new Set(state.goals.map(g => g.type));
    $("#goalPicker").innerHTML = GOALS.map(g => `<button type="button" class="goal-opt" data-goal="${g.type}" aria-pressed="${chosen.has(g.type)}"><b>${g.title}</b><span>${g.desc}</span></button>`).join("");
    const w = WEIGHTS[state.goals.length] || [];
    $("#goalOrder").innerHTML = state.goals.map((g, i) => {
      const def = GOALS.find(x => x.type === g.type);
      let fields = "";
      if (g.type === "emergency_fund") fields = `<div class="field"><label for="g-mo">Size</label><select id="g-mo" data-gk="months_of_expenses"><option value="3" ${g.months_of_expenses != 6 ? "selected" : ""}>3 months of essentials</option><option value="6" ${g.months_of_expenses == 6 ? "selected" : ""}>6 months of essentials</option></select></div>`;
      if (g.type === "save_for_purchase") fields = `
        <div class="field grow"><label for="g-lb">Saving for</label><input id="g-lb" data-gk="label" value="${esc(g.label || "")}" placeholder="e.g. a down payment"></div>
        <div class="field"><label for="g-ta">Target amount</label><input id="g-ta" data-gk="target_amount" inputmode="decimal" value="${esc(g.target_amount || "")}"></div>
        <div class="field"><label for="g-sv">Already saved</label><input id="g-sv" data-gk="saved" inputmode="decimal" value="${esc(g.saved || "")}"></div>
        <div class="field"><label for="g-tm">Within (months)</label><input id="g-tm" data-gk="target_months" inputmode="numeric" value="${esc(g.target_months || "")}" placeholder="optional"></div>`;
      if (g.type === "pay_off_car" || g.type === "pay_off_mortgage") fields = `<div class="field"><label for="g-tm-${g.type}">Pay off within (months)</label><input id="g-tm-${g.type}" data-gk="target_months" inputmode="numeric" value="${esc(g.target_months || "")}" placeholder="optional"></div>`;
      return `<li class="goal-item" data-gi="${i}">
        <div class="goal-item-head"><strong>${def.title}</strong><span class="share">${Math.round((w[i] || 0) * 100)}% of free cash to start</span>
          <button type="button" class="icon-btn" data-move="-1" aria-label="Move up" ${i === 0 ? "disabled" : ""}>&uarr;</button>
          <button type="button" class="icon-btn" data-move="1" aria-label="Move down" ${i === state.goals.length - 1 ? "disabled" : ""}>&darr;</button>
          <button type="button" class="icon-btn" data-remove-goal aria-label="Remove goal">&times;</button></div>
        ${fields ? `<div class="goal-fields">${fields}</div>` : ""}
      </li>`;
    }).join("");
    $("#goalEmpty").hidden = state.goals.length > 0;
    $("#investPrefs").hidden = !chosen.has("invest");
    const inv = state.investing;
    $$('input[name="asset"]').forEach(c => (c.checked = inv.assets.includes(c.value)));
    $$('input[name="risk"]').forEach(r => (r.checked = r.value === inv.risk));
    $("#horizon").value = inv.horizon_years;
    $("#screen").value = inv.screen;
    $("#customValues").value = inv.custom_values || "";
    markDone();
  }
  function bindGoals() {
    $("#goalPicker").addEventListener("click", e => {
      const b = e.target.closest("[data-goal]");
      if (!b) return;
      const t = b.dataset.goal;
      const i = state.goals.findIndex(g => g.type === t);
      if (i >= 0) state.goals.splice(i, 1);
      else state.goals.push({ type: t, months_of_expenses: 3 });
      renderGoals();
    });
    $("#goalOrder").addEventListener("click", e => {
      const li = e.target.closest("[data-gi]");
      if (!li) return;
      const i = Number(li.dataset.gi);
      if (e.target.dataset.move) {
        const j = i + Number(e.target.dataset.move);
        [state.goals[i], state.goals[j]] = [state.goals[j], state.goals[i]];
        renderGoals();
      } else if (e.target.hasAttribute("data-remove-goal")) {
        state.goals.splice(i, 1);
        renderGoals();
      }
    });
    $("#goalOrder").addEventListener("input", e => {
      const li = e.target.closest("[data-gi]");
      if (li && e.target.dataset.gk) state.goals[Number(li.dataset.gi)][e.target.dataset.gk] = e.target.value;
    });
    $("#goalOrder").addEventListener("change", e => {
      const li = e.target.closest("[data-gi]");
      if (li && e.target.dataset.gk) state.goals[Number(li.dataset.gi)][e.target.dataset.gk] = e.target.value;
    });
    $$('input[name="asset"]').forEach(c => c.addEventListener("change", () => {
      state.investing.assets = $$('input[name="asset"]:checked').map(x => x.value);
    }));
    $$('input[name="risk"]').forEach(r => r.addEventListener("change", () => { state.investing.risk = r.value; }));
    $("#horizon").addEventListener("input", e => { state.investing.horizon_years = num(e.target.value) || 10; });
    $("#screen").addEventListener("change", e => { state.investing.screen = e.target.value; state.investing.choices = {}; });
    $("#customValues").addEventListener("input", e => { state.investing.custom_values = e.target.value; });
  }

  // ---------------------------------------------------------------- step 5: the plan
  function profile(explain) {
    return {
      income: state.income, current_savings: state.current_savings,
      expenses: state.expenses.filter(e => e.subcategory).map(e => ({
        description: e.description, amount: e.amount, frequency: e.frequency, monthly_amount: e.monthly_amount ?? toMonthly(e.amount, e.frequency),
        category: e.category, subcategory: e.subcategory, type: e.type,
      })),
      debts: state.debts, goals: state.goals, debt_method: state.debt_method,
      spending_cut_pct: state.spending_cut_pct, investing: state.investing, explain,
    };
  }
  async function buildPlan(explain) {
    if (incomeMonthly() <= 0) {
      $("#planEmpty").hidden = false;
      $("#plan").hidden = true;
      return;
    }
    const unsorted = state.expenses.filter(e => !e.subcategory).length;
    if (unsorted) await sortExpenses();
    $("#planEmpty").hidden = true;
    $("#plan").hidden = false;
    $("#storySource").textContent = explain && window.APP.ai ? "Gemini is writing your summary..." : "Updating...";
    try {
      const plan = await api("/api/plan", profile(explain));
      lastPlan = plan;
      renderPlan(plan, explain);
    } catch (err) {
      $("#storySource").textContent = err.message;
    }
  }
  function renderPlan(p, explained) {
    // story
    const n = p.narrative;
    $("#storySource").textContent = p.narrative_source === "gemini" ? "Summary written by Gemini from the numbers below" : (p.ai_notice ? p.ai_notice + " Showing the built-in summary." : "Built-in summary (no AI)");
    $("#storyHeadline").textContent = n.headline;
    $("#storySummary").textContent = n.summary;
    $("#storySteps").innerHTML = n.this_month.map(s => `<li>${esc(s)}</li>`).join("");
    $("#storyWatch").innerHTML = (n.watch_outs || []).map(s => `<li>${esc(s)}</li>`).join("");
    $("#storyEnd").textContent = n.encouragement || "";
    $("#reExplain").hidden = !(window.APP.ai && !explained);

    // where each dollar goes
    const cf = p.cash_flow, bt = p.spending.by_type;
    const segs = [
      { label: "Needs", value: bt.need || 0, color: css("--need") },
      { label: "Debt payments", short: "Debt", value: cf.debt_payments, color: css("--debt") },
      { label: "Wants", value: (bt.want || 0) + (bt.other || 0), color: css("--want") },
      { label: "Giving", value: bt.giving || 0, color: css("--give") },
      { label: "Free for goals", short: "Goals", value: Math.max(0, cf.free_cash), color: css("--free") },
    ];
    window.Charts.stack($("#ruleBar"), segs, { legend: $("#ruleNote") });
    const r = p.budget_rule;
    const note = document.createElement("p");
    note.className = "hint";
    note.textContent = `50/30/20 check: needs and debt payments take ${r.needs_pct}% of take-home pay (guideline 50%), wants and giving ${r.wants_pct}% (30%), and ${r.savings_pct}% is left for savings and goals (20%).`
      + (cf.savings_transfers ? ` Your ${money(cf.savings_transfers)} monthly savings transfer counts as money for goals, not spending.` : "")
      + (p.spending.moved_to_debts.length ? ` Loan payments you listed as expenses are counted in Debts instead.` : "");
    $("#ruleNote").appendChild(note);

    // goals
    $("#goalCards").innerHTML = p.goals.length ? p.goals.map((g, i) => goalCard(g, i, p)).join("")
      : `<p class="empty">No goals chosen. Go back to step 4 to pick some.</p>`;

    // timeline
    const h = p.timeline.history;
    const series = [];
    if (p.debts.items.length) series.push({ name: "Debt owed", color: css("--debt"), values: h.debt });
    if (h.saved.some(v => v > 0)) series.push({ name: "Savings", color: css("--save"), values: h.saved });
    if (h.invest.some(v => v > 0)) series.push({ name: "Investments (illustration)", color: css("--free"), values: h.invest });
    // Show the years that matter: the investing horizon and every goal, not a
    // 30-year mortgage tail (unless paying off the mortgage is a goal).
    const goalMonths = p.timeline.milestones.filter(m => m.kind === "goal").map(m => m.month);
    const span = Math.min(h.debt.length, Math.max(24, (p.investing.horizon_years || 10) * 12, ...goalMonths.map(m => m + 6)));
    series.forEach(s => (s.values = s.values.slice(0, span)));
    if (series.length) {
      window.Charts.lines($("#timelineChart"), { series, markers: p.timeline.milestones.filter(m => m.kind === "goal").map(m => ({ month: m.month, color: css("--free") })) });
      $("#timelineChart").hidden = false;
    } else $("#timelineChart").hidden = true;
    $("#milestones").innerHTML = p.timeline.milestones.length
      ? p.timeline.milestones.map(m => `<li class="ms-${m.kind}"><time>${esc(m.date)}</time><span>${esc(m.label)}</span></li>`).join("")
      : `<li><time>-</time><span>No milestones yet - add goals or free up cash.</span></li>`;

    renderDebtBlock(p);
    renderInvestBlock(p);

    window.Charts.bars($("#planSpend"), p.spending.by_category.map(c => {
      const main = c.subcategories.reduce((a, s) => (a[s.type] = (a[s.type] || 0) + s.amount, a), {});
      const t = Object.entries(main).sort((a, b) => b[1] - a[1])[0]?.[0];
      return { label: c.category, value: c.amount, color: typeColor(t) };
    }));

    const chips = ["When will I be debt-free?", "Avalanche or snowball for me?", "Where can I cut spending?", "Can I afford a $300 car payment increase?"];
    if (p.goals.some(g => g.type === "invest")) chips.push("Explain my investing mix");
    $("#askChips").innerHTML = chips.map(c => `<button type="button" class="chip" data-ask="${esc(c)}">${esc(c)}</button>`).join("");
    markDone();
  }
  function goalCard(g, i, p) {
    let detail = "";
    const done = g.done_label ? `Done by <b>${esc(g.done_label)}</b>.` : `Not reached within 30 years at this pace.`;
    if (g.type === "emergency_fund") {
      const start = num(state.current_savings);
      const pct = g.target ? Math.min(100, 100 * start / g.target) : 0;
      detail = `Target ${money(g.target)} (${g.months_of_expenses} months of essentials). You have ${money(start)} now. ${done}<div class="progress" aria-hidden="true"><span style="width:${pct}%"></span></div>`;
    } else if (g.type === "pay_off_cards") {
      const s = p.strategies;
      detail = `Extra money on top of your minimums, ${p.debt_method === "snowball" ? "smallest balance first" : "highest interest first"}. ${done}`;
      if (s && s.minimums_only.months) detail += ` Paying only minimums would take ${s.minimums_only.months} months.`;
    } else if (g.type === "pay_off_car" || g.type === "pay_off_mortgage") {
      detail = (g.loans || []).map(l => {
        let t = `${esc(l.name)}: finishes <b>${l.months_saved ?? 0} months sooner</b> and saves about <b>${money(l.interest_saved)}</b> in interest at this starting amount.`;
        if (l.target_months) t += ` To finish within ${l.target_months} months you would need about ${money(l.extra_needed_for_target)} extra a month.`;
        return t;
      }).join(" ") || "Add this loan in step 3 to see the effect.";
      detail += ` ${done}`;
    } else if (g.type === "save_for_purchase") {
      detail = `Target ${money(g.target)}. ${done}`;
      if (g.needed_per_month_for_target) detail += ` To hit your date you need ${money(g.needed_per_month_for_target)} a month - ${g.on_track ? "you're on track" : "you're behind; move this goal up or free more cash"}.`;
    } else if (g.type === "invest") {
      const pr = p.investing.projection || {};
      detail = `If returns averaged ${(p.investing.illustrative_return * 100).toFixed(0)}% a year, this could grow to about <b>${money(pr.value)}</b> in ${pr.years} years from ${money(pr.contributed)} put in. This is an illustration, not a promise - markets go down as well as up.`;
    }
    return `<article class="goal-card"><span class="rank">${i + 1}</span><h3>${esc(g.label)}</h3>
      <p class="amt">${money(g.first_month_amount)}<small>a month to start</small></p>
      <p class="detail">${detail}</p></article>`;
  }
  function renderDebtBlock(p) {
    const d = p.debts;
    $("#debtBlock").hidden = !d.items.length;
    if (!d.items.length) return;
    const t = p.timeline;
    const stats = [
      [money(d.total_balance), "total owed"],
      [money(d.monthly_payments), "monthly payments"],
      [money(d.monthly_interest), "interest this month"],
      [d.dti !== null ? d.dti + "%" : "-", `debt-to-income (${d.dti_basis})`],
    ];
    if (d.card_utilization !== null) stats.push([d.card_utilization + "%", "card utilization"]);
    if (t.has_mortgage && t.non_mortgage_free_date) stats.push([t.non_mortgage_free_date, "free of all but the mortgage"]);
    else if (t.debt_free_date) stats.push([t.debt_free_date, "debt-free"]);
    let html = `<div class="stat-row">${stats.map(([b, s]) => `<div class="stat"><b>${esc(b)}</b><span>${esc(s)}</span></div>`).join("")}</div>`;
    html += `<div class="table-wrap"><table><thead><tr><th>Debt</th><th class="num">Balance</th><th class="num">APR</th><th class="num">Payment</th><th class="num">Interest / mo</th></tr></thead><tbody>`
      + d.items.map(x => `<tr><td>${esc(x.name)}<br><span class="sub">${esc(x.kind_label)}${x.estimated_payment ? " - payment estimated" : ""}</span></td><td class="num">${money(x.balance)}</td><td class="num">${x.apr}%</td><td class="num">${money(x.payment)}</td><td class="num">${money(x.monthly_interest)}</td></tr>`).join("")
      + `</tbody></table></div>`;
    $("#debtSummary").innerHTML = html;
    const s = p.strategies;
    if (s) {
      const rows = [
        ["Minimum payments only", s.minimums_only, ""],
        [`Avalanche: highest interest first (+${money(s.extra_per_month)}/mo)`, s.avalanche, s.avalanche.order.join(", then ")],
        [`Snowball: smallest balance first (+${money(s.extra_per_month)}/mo)`, s.snowball, s.snowball.order.join(", then ")],
      ];
      const best = s.extra_per_month > 0 ? (s.avalanche.interest <= s.snowball.interest ? 1 : 2) : -1;
      $("#strategyTable").innerHTML = `<h3 class="sub-h">Credit cards and small loans: three ways to pay them off</h3><div class="table-wrap"><table class="strategy"><thead><tr><th>Approach</th><th class="num">Months</th><th class="num">Interest paid</th><th>Order</th></tr></thead><tbody>`
        + rows.map(([name, r, order], i) => `<tr class="${i === best ? "best" : ""}"><td>${name}</td><td class="num">${r.months ?? "never"}</td><td class="num">${money(r.interest)}</td><td>${esc(order)}</td></tr>`).join("")
        + `</tbody></table></div>` + (s.extra_per_month <= 0 ? `<p class="hint">Add "Pay off credit cards" as a goal to put extra money toward them.</p>` : "");
    } else $("#strategyTable").innerHTML = "";
  }
  function renderInvestBlock(p) {
    const hasInvest = p.goals.some(g => g.type === "invest");
    $("#investBlock").hidden = !hasInvest;
    if (!hasInvest) return;
    const inv = p.investing;
    $("#investDisclaimer").textContent = inv.disclaimer;
    const colors = { us_stocks: css("--pen"), intl_stocks: css("--free"), bonds: css("--save"), real_estate: css("--give"), cash: css("--ink-3"), crypto: css("--want") };
    window.Charts.stack($("#mixBar"), inv.mix.map(s => ({ label: s.label, value: s.pct, color: colors[s.key] })));
    $("#sleeves").innerHTML = `<p class="hint">Example ${esc(inv.risk)} mix${inv.screen !== "none" ? ", filtered for " + esc(inv.screen_label) : ""}. Pick one option in each part to build your own list - the choice is yours.</p>`
      + inv.mix.map(s => `<div class="sleeve" data-sleeve="${s.key}">
        <div class="sleeve-head"><b>${esc(s.label)}</b><span>${s.pct}% &middot; about ${money(s.monthly)}/mo</span></div>
        <div class="opts">${s.options.length ? s.options.map(o => `
          <label class="opt"><input type="radio" name="pick-${s.key}" value="${esc(o.ticker)}" ${state.investing.choices[s.key] === o.ticker ? "checked" : ""}>
            <span class="tk">${o.kind === "Account" ? esc(o.name) : esc(o.ticker)} <span class="risk-dots" title="Risk ${o.risk} of 5">${"&#9679;".repeat(o.risk)}</span></span>
            ${o.kind === "Account" ? "" : `<span class="nm">${esc(o.name)}</span>`}
            <span class="ab">${esc(o.about)}</span></label>`).join("") : `<p class="hint">No option in this list fits your values for this part.</p>`}</div></div>`).join("");
    renderPicks(inv);
    $("#investNotes").innerHTML = inv.notes.map(t => `<li>${esc(t)}</li>`).join("");
  }
  function renderPicks(inv) {
    const rows = inv.mix.filter(s => state.investing.choices[s.key]);
    $("#picks").innerHTML = rows.length ? `<h3 class="sub-h">Your picks</h3><div class="table-wrap"><table><thead><tr><th>Part</th><th>Your choice</th><th class="num">Monthly</th></tr></thead><tbody>`
      + rows.map(s => { const o = s.options.find(x => x.ticker === state.investing.choices[s.key]); return `<tr><td>${esc(s.label)}</td><td>${esc(o.kind === "Account" ? o.name : o.ticker + " - " + o.name)}</td><td class="num">${money(s.monthly)}</td></tr>`; }).join("")
      + `</tbody></table></div><p class="hint">Before buying, read each fund's fact sheet for its fees and holdings.</p>` : "";
  }
  function bindPlan() {
    let timer;
    $("#cut").addEventListener("input", e => {
      state.spending_cut_pct = Number(e.target.value);
      $("#cutOut").textContent = e.target.value + "%";
      renderStub();
      clearTimeout(timer);
      timer = setTimeout(() => buildPlan(false), 350);
    });
    $("#reExplain").addEventListener("click", () => buildPlan(true));
    $("#sleeves").addEventListener("change", e => {
      const sl = e.target.closest("[data-sleeve]");
      if (!sl) return;
      state.investing.choices[sl.dataset.sleeve] = e.target.value;
      renderPicks(lastPlan.investing);
    });
    $("#askChips").addEventListener("click", e => { if (e.target.dataset.ask) ask(e.target.dataset.ask); });
    $("#askForm").addEventListener("submit", e => {
      e.preventDefault();
      const q = $("#askInput").value.trim();
      if (q) { $("#askInput").value = ""; ask(q); }
    });
    $("#printPlan").addEventListener("click", () => window.print());
  }
  async function ask(question) {
    const chat = $("#chat");
    chat.insertAdjacentHTML("beforeend", `<div class="bubble user">${esc(question)}</div><div class="bubble bot wait">Thinking...</div>`);
    const wait = chat.lastElementChild;
    try {
      const r = await api("/api/ask", { question, profile: profile(false), history: state.chat });
      wait.classList.remove("wait");
      wait.textContent = r.answer;
      state.chat.push({ role: "user", text: question }, { role: "assistant", text: r.answer });
    } catch (err) {
      wait.textContent = err.message;
    }
  }

  // ---------------------------------------------------------------- sample household
  async function loadSample() {
    try {
      const s = await api("/api/sample");
      state.income = {
        paychecks: s.income.paychecks.map(p => ({ id: uid(), ...p })),
        other: (s.income.other || []).map(o => ({ id: uid(), ...o })),
      };
      state.current_savings = s.current_savings;
      state.expenses = s.expenses.map(e => ({ id: uid(), ...e }));
      state.debts = s.debts.map(d => ({ id: uid(), ...d }));
      state.goals = s.goals.map(g => ({ ...g }));
      state.debt_method = s.debt_method || "avalanche";
      state.investing = { choices: {}, ...s.investing };
      state.spending_cut_pct = 0;
      $("#cut").value = 0; $("#cutOut").textContent = "0%";
      $$('input[name="method"]').forEach(r => (r.checked = r.value === state.debt_method));
      renderIncome(); renderDebts(); renderExpenses();
      await sortExpenses();
      toast("Loaded a fictional household. Click any step to see or change its numbers.");
      go(5);
    } catch (err) {
      toast(err.message);
    }
  }

  // ---------------------------------------------------------------- start
  async function init() {
    try {
      TAXONOMY = await api("/api/categories");
      TAXONOMY.forEach(g => g.subcategories.forEach(s => (SUBS[s.name] = { category: g.category, type: s.type })));
    } catch (err) { toast("Could not load categories: " + err.message); }
    bindIncome(); bindUploads(); bindExpenses(); bindDebts(); bindGoals(); bindPlan();
    $$(".step-btn").forEach(b => b.addEventListener("click", () => go(b.dataset.step)));
    $$("[data-go]").forEach(b => b.addEventListener("click", () => go(b.dataset.go)));
    $("#loadSample").addEventListener("click", loadSample);
    renderIncome(); renderExpenses(); renderDebts();
  }
  init();
})();
