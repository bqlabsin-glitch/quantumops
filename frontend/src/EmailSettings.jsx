import React, {useEffect, useState} from 'react';

export default function EmailSettings({api}) {
  const [form, setForm] = useState(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {api('platform-admin/email/').then(x => setForm({...x,password:''})).catch(e => setMessage(e.message));}, []);
  const change = e => setForm({...form,[e.target.name]:e.target.type==='checkbox'?e.target.checked:e.target.value});
  async function save(e) {
    e.preventDefault(); setBusy(true); setMessage('');
    try {
      const {password_set,...payload}=form;
      const result=await api('platform-admin/email/',{method:'PUT',body:JSON.stringify({...payload,port:Number(payload.port)})});
      setForm({...result,password:''}); setMessage('Email settings saved.');
    } catch(e) {setMessage(e.message);} finally {setBusy(false);}
  }
  async function test() {
    setBusy(true); setMessage('');
    try {setMessage((await api('platform-admin/email/test/',{method:'POST'})).detail);}
    catch(e) {setMessage(e.message);} finally {setBusy(false);}
  }
  return <section className="panel admin-panel" style={{marginBottom:'1.5rem'}}>
    <h2>Email delivery</h2>
    <p>Configure this later when your provider details are ready. Verification codes and invitations need enabled email delivery.</p>
    {message&&<p role="status">{message}</p>}
    {form&&<form onSubmit={save}>
      <label className="check"><input name="enabled" type="checkbox" checked={form.enabled} onChange={change}/> Enable email delivery</label>
      <div className="two"><label>SMTP host<input name="host" value={form.host} onChange={change} placeholder="smtp.your-provider.com" required={form.enabled}/></label>
      <label>Port<input name="port" type="number" min="1" max="65535" value={form.port} onChange={change} required/></label></div>
      <label>Connection security<select name="security" value={form.security} onChange={change}><option value="STARTTLS">STARTTLS (usually port 587)</option><option value="SSL">SSL (usually port 465)</option></select></label>
      <label>Sender email<input name="from_email" type="email" value={form.from_email} onChange={change} required={form.enabled}/></label>
      <label>SMTP username<input name="username" value={form.username} onChange={change} autoComplete="off"/></label>
      <label>SMTP password or app password<input name="password" type="password" value={form.password} onChange={change} autoComplete="new-password" placeholder={form.password_set?'Saved — leave blank to keep it':'Enter when ready'}/></label>
      <p className="helper">Passwords are encrypted when stored and never displayed. Save changes before sending a test to your administrator email.</p>
      <div className="hero-actions"><button className="button primary" disabled={busy}>Save email settings</button><button type="button" className="button quiet" disabled={busy||!form.enabled} onClick={test}>Send test email</button></div>
    </form>}
  </section>;
}
