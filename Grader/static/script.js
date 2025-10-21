const form = document.getElementById("form");
const resultBox = document.getElementById("result");

form.onsubmit = async e => {
  e.preventDefault();
  resultBox.textContent = "Running...";
  const fd = new FormData(form);
  const res = await fetch("/submit", { method: "POST", body: fd });
  const data = await res.json();

  let msg = `Status: ${data.status}\n`;
  if (data.output) msg += `Output:\n${data.output}\n`;
  if (data.compile_log) msg += `\nCompiler log:\n${data.compile_log}\n`;

  resultBox.textContent = msg;
};