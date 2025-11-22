function showSections() {
  document.querySelectorAll(".hidden").forEach(el => {
    el.classList.remove("hidden");
  });
}

async function analyzeChat(messages) {
  const response = await fetch("http://127.0.0.1:8000/analyze-chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages })
  });

  return await response.json();
}

document.getElementById("analyzeBtn").addEventListener("click", async () => {

  const rawText = document.getElementById("inputBox").value;
  const messages = rawText.split("\n").filter(m => m.trim() !== "");

  const result = await analyzeChat(messages);

  // Show sections after click
  showSections();

  document.getElementById("tags").innerHTML = "";
  document.getElementById("breakdown").innerHTML = "";
  document.getElementById("trendBox").innerHTML = "";

  // Emotion Colors
  const emotionColors = {
    admiration: "#6A5ACD", amusement: "#FFB347", anger: "#FF4500",
    annoyance: "#FF6347", approval: "#4B0082", caring: "#DB7093",
    confusion: "#8A2BE2", curiosity: "#20B2AA", desire: "#FF69B4",
    disappointment: "#708090", disapproval: "#A52A2A", disgust: "#556B2F",
    embarrassment: "#CD5C5C", excitement: "#FFA500", fear: "#8B0000",
    gratitude: "#32CD32", grief: "#2F4F4F", joy: "#FFD700",
    love: "#FF1493", nervousness: "#E9967A", optimism: "#00FA9A",
    pride: "#4682B4", realization: "#7B68EE", relief: "#87CEEB",
    remorse: "#8B4513", sadness: "#1E90FF", surprise: "#00CED1",
    neutral: "#604b61ff"
  };

  // Trend text
  document.getElementById("trendBox").innerHTML = result.emotional_trend;

  // Summary tags
  const distribution = result.emotion_distribution;
  Object.keys(distribution).forEach(emotion => {
    const tag = document.createElement("span");
    const color = emotionColors[emotion] || "#888";
    tag.className = "tag";
    tag.style.borderColor = color;
    tag.style.color = color;
    tag.textContent = `${emotion} (${distribution[emotion]})`;
    document.getElementById("tags").appendChild(tag);
  });

  // Breakdown
  result.timeline.forEach((item, index) => {
    const div = document.createElement("div");
    div.className = "msgItem";

    const color = emotionColors[item.emotion] || "#888";

    div.innerHTML = `
      <b>${index + 1}. "${item.text}"</b><br>
      Emotion: 
      <span class="emotionLabel" style="background:${color}">${item.emotion}</span>
    `;

    document.getElementById("breakdown").appendChild(div);
  });

  // Line Chart
  new Chart(document.getElementById("timelineChart"), {
    type: "line",
    data: {
      labels: result.timeline.map((_, i) => `Message ${i + 1}`),
      datasets: [{
        label: "Intensity",
        data: result.timeline.map(t => t.score),
        borderColor: "#38bdf8",
        pointBackgroundColor: result.timeline.map(t => emotionColors[t.emotion]),
        borderWidth: 3,
        tension: 0.4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: { y: { min: 0, max: 1 } }
    }
  });

  // Pie Chart
  new Chart(document.getElementById("pieChart"), {
    type: "pie",
    data: {
      labels: Object.keys(distribution),
      datasets: [{
        data: Object.values(distribution),
        backgroundColor: Object.keys(distribution).map(e => emotionColors[e])
      }]
    },
    options: {
      responsive: true
    }
  });

  // Bar Chart
  new Chart(document.getElementById("barChart"), {
    type: "bar",
    data: {
      labels: Object.keys(distribution),
      datasets: [{
        label: "Count",
        data: Object.values(distribution),
        backgroundColor: Object.keys(distribution).map(e => emotionColors[e])
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { beginAtZero: true }
      }
    }
  });

});