const $ = q => document.querySelector(q);

$("#loginBtn").onclick = () => window.location = "/authorize";

// Add example click handlers
document.querySelectorAll('.example').forEach(example => {
  example.onclick = () => {
    $("#prompt").value = example.textContent;
    $("#prompt").focus();
  }
});

function createSlotCard(slotText) {
  // Split the slot text into its components
  const [slotLine, dateLine, timeLine] = slotText.split('\n');
  const slotNumber = slotLine.replace('Slot ', '');
  
  // Extract date and time information
  const [dayOfWeek, timeRange] = timeLine.split(' | ');
  const [localTime, utcTime] = timeRange.split(' | ');
  const [startTime, endTime] = localTime.split('-');
  
  const card = document.createElement('div');
  card.className = 'slot-card';
  card.innerHTML = `
    <div class="slot-header">Slot ${slotNumber}</div>
    <div class="slot-date">
      <div class="slot-date-value">${dateLine}</div>
    </div>
    <div class="slot-time">${timeLine}</div>
    <button class="book-btn" onclick="bookSlot(this)" data-date="${dateLine}" data-time="${localTime}">
      Book this slot
    </button>
  `;
  return card.outerHTML;
}

// Modal handling
const modal = $("#bookingModal");
const modalDateTime = $("#modalDateTime");
let activeBookingButton = null;

function showModal(date, timeRange, button) {
  modalDateTime.textContent = `${date} | ${timeRange}`;
  modal.classList.add('active');
  activeBookingButton = button;
  $("#meetingTitle").focus();
}

function hideModal() {
  modal.classList.remove('active');
  $("#bookingForm").reset();
  activeBookingButton = null;
}

// Close modal when clicking outside
modal.addEventListener('click', (e) => {
  if (e.target === modal) hideModal();
});

// Cancel button handler
$("#cancelBooking").onclick = hideModal;

// Form submission handler
$("#bookingForm").onsubmit = async (e) => {
  e.preventDefault();
  
  if (!activeBookingButton) return;
  
  const date = activeBookingButton.dataset.date;
  const timeRange = activeBookingButton.dataset.time;
  const [startTime, endTime] = timeRange.split('-').map(t => t.trim());
  
  // Combine date and time
  const startDateTime = `${date} ${startTime}`;
  const endDateTime = `${date} ${endTime}`;
  
  const title = $("#meetingTitle").value.trim();
  const attendeesInput = $("#attendees").value.trim();
  const attendees = attendeesInput ? attendeesInput.split(',').map(email => email.trim()).filter(Boolean) : [];
  
  // Disable the form and show loading state
  const submitBtn = $("#confirmBooking");
  submitBtn.disabled = true;
  submitBtn.innerHTML = `
    <svg class="animate-spin" width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
    Booking...
  `;
  
  try {
    const res = await fetch("/create-event", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        prompt: `Create event ${title} from ${startDateTime} to ${endDateTime}`,
        attendees: attendees
      })
    });
    
    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.error || 'Failed to book slot');
    }
    
    const result = await res.json();
    
    // Update the original button to show success
    activeBookingButton.className = 'book-btn success';
    activeBookingButton.innerHTML = `
      <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
      </svg>
      Booked!${attendees.length ? ` (${attendees.length} attendee${attendees.length === 1 ? '' : 's'})` : ''}
    `;
    activeBookingButton.disabled = true;
    
    // Hide the modal
    hideModal();
    
  } catch (err) {
    console.error('Booking error:', err);
    submitBtn.disabled = false;
    submitBtn.innerHTML = 'Book Meeting';
    alert(`Failed to book slot: ${err.message}`);
  }
};

function bookSlot(button) {
  const date = button.dataset.date;
  const timeRange = button.dataset.time;
  showModal(date, timeRange, button);
}

function showLoading() {
  $("#slots-container").innerHTML = `
    <div class="loading">
      <svg class="animate-spin" width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
      </svg>
      Finding available slots...
    </div>
  `;
}

function showError(message) {
  $("#slots-container").innerHTML = `
    <div class="error">
      <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
      ${message}
    </div>
  `;
}

$("#findBtn").onclick = async () => {
  const prompt = $("#prompt").value.trim();
  if (!prompt) {
    showError("Please enter a description of when you'd like to meet.");
    return;
  }

  $("#findBtn").disabled = true;
  showLoading();
  
  try {
    const res = await fetch("/free-slots", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({prompt})
    });

    if (res.status === 401) {
      showError("Not authorized – please click the Authorize Access button first.");
      return;
    }

    const text = await res.text();
    console.log('Raw response:', text);

    if (!text || text === "No available slots found.") {
      showError("No slots found matching your criteria. Try different dates or times.");
      return;
    }

    // Split response into individual slots (separated by double newlines)
    const slots = text.split('\n\n').filter(Boolean);
    
    if (slots.length === 0) {
      showError("No slots found matching your criteria. Try different dates or times.");
      return;
    }

    // Create and display slot cards
    const html = slots.map(createSlotCard).join('');
    const container = $("#slots-container");
    container.innerHTML = html;

  } catch (err) {
    console.error('Error details:', err);
    showError("An error occurred while finding slots. Please try again.");
  } finally {
    $("#findBtn").disabled = false;
  }
};
