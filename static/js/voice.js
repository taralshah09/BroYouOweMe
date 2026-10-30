(() => {
  const byId = id => document.getElementById(id);
  const form = byId('voice-review'), record = byId('voice-record'), stop = byId('voice-stop');
  const parse = byId('voice-parse'), text = byId('voice-transcript');
  const status = byId('voice-status'), error = byId('voice-error');
  const csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
  let recorder, stream, timer, busy = false;
  const release = () => {clearTimeout(timer); stream?.getTracks().forEach(track => track.stop());};
  const resetApproval = () => {form.elements.approved.checked = false;};
  text.addEventListener('input', resetApproval);
  form.addEventListener('input', event => {if (event.target.name !== 'approved') resetApproval();});
  function setBusy(value) {
    busy = value;
    record.disabled = value; parse.disabled = value; byId('voice-save').disabled = value;
  }
  async function draft(body, json = false) {
    setBusy(true); error.textContent = ''; status.textContent = 'Preparing your draft…'; resetApproval();
    try {
      const response = await fetch(`/groups/${form.dataset.group}/voice/parse`, {
        method: 'POST', headers: {'X-CSRFToken': csrf, ...(json ? {'Content-Type': 'application/json'} : {})}, body
      });
      const result = await response.json();
      if (typeof result.transcript === 'string') text.value = result.transcript;
      if (!response.ok) throw new Error(result.error || JSON.stringify(result.errors || 'Unable to prepare draft.'));
      const data = result.draft;
      form.elements.amount.value = data.amount || '';
      form.elements.description.value = data.description;
      form.elements.paid_by.value = data.paid_by || '';
      form.elements.split_mode.value = 'equal';
      form.elements.split_mode.dispatchEvent(new Event('change'));
      form.elements.participants.required = data.participants.length === 0;
      for (const option of form.elements.participants.options) option.selected = data.participants.includes(Number(option.value));
      form.elements.category.value = ''; form.elements.tag.value = '';
      byId('voice-warnings').replaceChildren();
      for (const warning of data.warnings) {
        const item = document.createElement('li'); item.textContent = warning; byId('voice-warnings').append(item);
      }
      status.textContent = 'Draft ready. Check every field below, then approve to save.';
      form.elements.amount.focus();
    } catch (failure) {
      error.textContent = failure.message; status.textContent = 'Nothing has been saved.';
    } finally {setBusy(false);}
  }
  async function wav(blob) {
    const context = new AudioContext();
    try {
      const decoded = await context.decodeAudioData(await blob.arrayBuffer());
      // Trim recorder scheduling delays to the provider's 30-second limit.
      const length = Math.min(Math.ceil(decoded.duration * 16000), 30 * 16000);
      const offline = new OfflineAudioContext(1, length, 16000);
      const source = offline.createBufferSource(); source.buffer = decoded; source.connect(offline.destination); source.start();
      const rendered = await offline.startRendering();
      const samples = rendered.getChannelData(0), buffer = new ArrayBuffer(44 + samples.length * 2), view = new DataView(buffer);
      const str = (offset, value) => [...value].forEach((character, i) => view.setUint8(offset + i, character.charCodeAt(0)));
      str(0, 'RIFF'); view.setUint32(4, buffer.byteLength - 8, true); str(8, 'WAVE'); str(12, 'fmt ');
      view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
      view.setUint32(24, 16000, true); view.setUint32(28, 32000, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
      str(36, 'data'); view.setUint32(40, samples.length * 2, true);
      samples.forEach((sample, i) => view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, sample)) * (sample < 0 ? 32768 : 32767), true));
      return new Blob([buffer], {type: 'audio/wav'});
    } finally {await context.close();}
  }
  record.addEventListener('click', async () => {
    if (busy) return;
    error.textContent = ''; setBusy(true); resetApproval();
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw new Error('Microphone recording requires HTTPS or localhost and a supported browser. You can type a transcript instead.');
      stream = await navigator.mediaDevices.getUserMedia({audio: true});
      const chunks = []; recorder = new MediaRecorder(stream);
      recorder.addEventListener('dataavailable', event => {if (event.data.size) chunks.push(event.data);});
      recorder.addEventListener('stop', async () => {
        release(); stop.disabled = true;
        try {
          status.textContent = 'Transcribing your recording…';
          const body = new FormData(); body.append('audio', await wav(new Blob(chunks, {type: recorder.mimeType})), 'recording.wav');
          await draft(body);
        } catch (failure) {error.textContent = failure.message; status.textContent = 'Nothing has been saved.'; setBusy(false);}
      });
      recorder.addEventListener('error', () => {release(); error.textContent = 'Recording failed. Please try again.'; stop.disabled = true; setBusy(false);});
      recorder.start(); stop.disabled = false;
      status.textContent = 'Recording… stops automatically after 30 seconds.';
      timer = setTimeout(() => {if (recorder.state === 'recording') recorder.stop();}, 30000);
    } catch (failure) {release(); error.textContent = failure.message; status.textContent = 'You can type a transcript below.'; setBusy(false);}
  });
  stop.addEventListener('click', () => {if (recorder?.state === 'recording') recorder.stop();});
  parse.addEventListener('click', () => {if (!busy) draft(JSON.stringify({transcript: text.value}), true);});
  window.addEventListener('pagehide', release);
  form.addEventListener('submit', () => {byId('voice-save').disabled = true;});
})();
