const $ = q => document.querySelector(q);

$("#loginBtn").onclick = () => window.location = "/authorize";

// Add example click handlers
document.querySelectorAll('.example').forEach(example => {
  example.onclick = () => {
    $("#prompt").value = example.textContent;
    $("#prompt").focus();
  }
});

$("#findBtn").onclick = async () => {
  $("#out").textContent = "⌛ Finding available slots...";
  $("#findBtn").disabled = true;
  
  try {
    const res = await fetch("/free-slots", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({prompt: $("#prompt").value.trim()})
    });

    if (res.status === 401) {
      $("#out").textContent = "⚠️ Not authorized – please click the Authorize Access button first.";
      return;
    }

    const text = await res.text();
    $("#out").textContent = text || "No slots found matching your criteria.";
  } catch (err) {
    $("#out").textContent = "⚠️ An error occurred while finding slots. Please try again.";
    console.error(err);
  } finally {
    $("#findBtn").disabled = false;
  }
};
