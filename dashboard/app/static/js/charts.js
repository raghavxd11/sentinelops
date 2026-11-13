// Overview charts. Data comes from the server as JSON inside #chart-data.
// Colors are read from the CSS variables so charts follow the light/dark theme.
(function () {
  'use strict';

  var dataEl = document.getElementById('chart-data');
  if (!dataEl || !window.Chart) return;
  var data = JSON.parse(dataEl.textContent);

  // Fixed order and color per status, same as the status pills.
  var STATUSES = [
    { key: 'SUCCESS', label: 'Success', color: '--ok' },
    { key: 'FAILED', label: 'Failed', color: '--fail' },
    { key: 'ROLLED_BACK', label: 'Rolled back', color: '--warn' },
    { key: 'IN_PROGRESS', label: 'In progress', color: '--info' }
  ];

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  var charts = [];

  function draw() {
    charts.forEach(function (chart) { chart.destroy(); });
    charts = [];

    var surface = cssVar('--surface');
    var border = cssVar('--border');
    var text = cssVar('--text');
    var text2 = cssVar('--text-2');

    Chart.defaults.font.family = '"IBM Plex Sans", system-ui, sans-serif';
    Chart.defaults.font.size = 12;
    Chart.defaults.color = text2;
    Chart.defaults.animation = false;

    var tooltip = {
      backgroundColor: cssVar('--raised'),
      borderColor: border,
      borderWidth: 1,
      titleColor: text,
      bodyColor: text2,
      padding: 10,
      cornerRadius: 6,
      boxWidth: 8,
      boxHeight: 8,
      boxPadding: 4
    };

    // Deployments per day, stacked by status.
    var barEl = document.getElementById('perDayChart');
    if (barEl) {
      charts.push(new Chart(barEl, {
        type: 'bar',
        data: {
          labels: data.per_day.labels,
          datasets: STATUSES.map(function (status) {
            return {
              label: status.label,
              data: data.per_day.series[status.key],
              backgroundColor: cssVar(status.color),
              borderColor: surface,   // 1px gap between stacked segments
              borderWidth: 1,
              borderRadius: 2,
              maxBarThickness: 22
            };
          })
        },
        options: {
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          scales: {
            x: { stacked: true, grid: { display: false }, border: { color: border }, ticks: { maxRotation: 0, autoSkipPadding: 12 } },
            y: { stacked: true, beginAtZero: true, grid: { color: border, lineWidth: 1 }, border: { display: false }, ticks: { precision: 0, maxTicksLimit: 6 } }
          },
          plugins: {
            legend: { position: 'top', align: 'start', labels: { boxWidth: 8, boxHeight: 8, padding: 14, color: text2 } },
            tooltip: tooltip
          }
        }
      }));
    }

    // Status breakdown. The legend with counts is plain HTML next to the chart.
    var donutEl = document.getElementById('breakdownChart');
    if (donutEl) {
      charts.push(new Chart(donutEl, {
        type: 'doughnut',
        data: {
          labels: STATUSES.map(function (status) { return status.label; }),
          datasets: [{
            data: STATUSES.map(function (status) { return data.breakdown[status.key] || 0; }),
            backgroundColor: STATUSES.map(function (status) { return cssVar(status.color); }),
            borderColor: surface,
            borderWidth: 2
          }]
        },
        options: {
          maintainAspectRatio: false,
          cutout: '68%',
          plugins: { legend: { display: false }, tooltip: tooltip }
        }
      }));
    }
  }

  draw();
  document.addEventListener('themechange', draw);
})();
