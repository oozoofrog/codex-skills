import {fail} from './consult.mjs';
const picker='[data-testid="composer-intelligence-picker-content"]';
const input='#prompt-textarea[contenteditable="true"]';
const form='form[data-type="unified-composer"]';
const messages='[data-message-id][data-message-author-role]';
const sort=a=>[...a].sort();
const same=(a,b)=>JSON.stringify(sort(a))===JSON.stringify(sort(b));
const basename=p=>p.split('/').pop();
export function coversVisibleText(markdown,text) {
  const compact=value=>value.normalize('NFC').replace(/\s/gu,'');
  const copied=compact(markdown);let at=0;
  return [...compact(text)].every(character=>{const found=copied.indexOf(character,at);if(found<0)return false;at=found+character.length;return true;});
}
const safeId=id=>{if(!/^[a-zA-Z0-9:_-]+$/.test(id))fail('TURN_IDENTITY_AMBIGUOUS','Unsafe or absent DOM identity.');return id;};

/** Inject an already-authorized supported CUA tab. This module never opens tabs or accesses network/session internals. */
export class ChatAdapter {
  constructor(tab) { this.tab=tab; this.identity=tab; this.surface='chat'; this.expectedURL=null; }
  async inspect(destination) {
    const url=await this.tab.url();
    if ((destination.kind==='new' && !/^https:\/\/chatgpt\.com\/?$/.test(url)) ||
        (destination.kind==='existing' && url!==destination.url)) fail('TURN_IDENTITY_AMBIGUOUS','Open the exact requested destination before invoking the transport.');
    this.expectedURL=url;
    const state=await this.composer();
    if (!state.present) fail('AUTH_REQUIRED','No authenticated composer is available.');
    if (state.text || state.attachments.length || state.removable || state.running) fail('UI_DRIFT','The composer contains a draft, attachments, or an active response.');
    const turns=await this.read();
    if (destination.kind==='new' && turns.turns.length) fail('TURN_IDENTITY_AMBIGUOUS','A new destination already contains turns.');
    // Existing conversations no longer show the surface radio. Require the surface-specific composer signature.
    if(destination.kind==='existing') await this.assertSurface();
    return {turn_ids:turns.turns.map(t=>t.id)};
  }
  async composer() {
    return this.tab.playwright.evaluate(({input,form})=>{
      const e=document.querySelector(input), f=document.querySelector(form);
      return {removable:Array.from(f?.querySelectorAll('button[aria-label]')??[]).filter(e=>/(제거|Remove)/i.test(e.getAttribute('aria-label'))).length,present:!!e,text:e?Array.from(e.children).map(p=>p.innerText.replace(/\n$/,'')).join('\n').trim():'',attachments:Array.from(f?.querySelectorAll('[role="group"][aria-label]:has([data-default-action])')??[]).map(e=>e.getAttribute('aria-label')),
        running:Array.from(document.querySelectorAll('main button')).some(e=>/^(답변 중지|Stop generating|Stop response)$/.test(e.getAttribute('aria-label')??'')),
        buttons:Array.from(f?.querySelectorAll('button[aria-haspopup="menu"]')??[]).filter(e=>e.id!=='composer-plus-btn').map(e=>({text:e.innerText,label:e.getAttribute('aria-label')}))};
    },{input,form});
  }
  async assertSurface() {
    const radio=this.tab.playwright.getByRole('radio',{name:this.surface==='chat'?'Chat':'Work',exact:true});
    if(await radio.count()) {
      if(await radio.getAttribute('aria-checked')!=='true')fail('SURFACE_UNAVAILABLE','Requested surface is not selected.');
      return;
    }
    const state=await this.composer();
    const fullModel=state.buttons.some(b=>/^GPT-/.test(b.text));
    if (fullModel !== (this.surface==='work')) fail('SURFACE_UNAVAILABLE','Existing conversation surface cannot be verified from its composer.');
  }
  async openPicker() {
    const button=this.tab.playwright.locator(`${form} button[aria-haspopup="menu"]`).filter({visible:true});
    // Exactly the add-files control and one intelligence picker are expected.
    const controls=await button.all(); let trigger;
    for(const candidate of controls)if(await candidate.getAttribute('id')!=='composer-plus-btn'){if(trigger)fail('UI_DRIFT','Multiple configuration controls.');trigger=candidate;}
    if(!trigger)fail('UI_DRIFT','Intelligence picker is unavailable.');
    if(await trigger.getAttribute('aria-expanded')!=='true')await trigger.click();
    if(await this.tab.playwright.locator(picker).count()!==1)fail('UI_DRIFT','Picker identity is ambiguous.');
  }
  async settings() {
    return this.tab.playwright.evaluate(picker=>{
      const p=document.querySelector(picker);
      const models=Array.from(p?.querySelectorAll('[role="menuitemradio"]')??[]);
      const control=p?.querySelector('[aria-keyshortcuts="ArrowLeft ArrowRight"]');
      const label=(control?.getAttribute('aria-describedby')??'').split(' ').map(id=>document.getElementById(id)?.textContent??'').find(t=>t.includes(','));
      const slider=p?.querySelector('[role="slider"]');
      return {models:models.map(e=>e.textContent.trim()),model:models.filter(e=>e.getAttribute('aria-checked')==='true').map(e=>e.textContent.trim()),
        effort:label?.split(',')[0].trim(),index:Number(slider?.getAttribute('aria-valuenow')),max:Number(slider?.getAttribute('aria-valuemax'))};
    },picker);
  }
  async configure(target) {
    if(target.surface!==this.surface)fail('SURFACE_UNAVAILABLE','Use the matching surface adapter.');
    if((this.surface==='work'&&target.effort==='Pro')||(this.surface==='chat'&&['Ultra','울트라','Max'].includes(target.effort)))fail('EFFORT_UNAVAILABLE','Chat Pro and Work Max/Ultra are different controls.');
    const radio=this.tab.playwright.getByRole('radio',{name:this.surface==='chat'?'Chat':'Work',exact:true});
    if(await radio.count() && await radio.getAttribute('aria-checked')!=='true')await radio.click();
    await this.assertSurface(); await this.openPicker();
    let settings=await this.settings();
    if(!settings.models.includes(target.model))fail('MODEL_UNAVAILABLE',`The live ${this.surface} menu does not offer ${target.model}.`);
    if(settings.model.length!==1)fail('UI_DRIFT','The model selection is ambiguous.');
    if(settings.model[0]!==target.model) {
      // DOM snapshots can include inert submenu items. Always open the actual model submenu before clicking a model.
      await this.tab.playwright.locator(`${picker} [role="menuitem"][aria-expanded="false"]`).click();
      const model=this.tab.playwright.getByRole('menuitemradio',{name:target.model,exact:true});
      if(await model.evaluate(e=>!!e.closest('[inert]')))fail('UI_DRIFT','The model submenu did not open.');
      await model.click(); settings=await this.settings();
    }
    if(settings.model[0]!==target.model)fail('CONFIGURATION_MISMATCH','Model selection did not apply.');
    const control=this.tab.playwright.locator(`${picker} [aria-keyshortcuts="ArrowLeft ArrowRight"]`);
    // Descend first, then inspect named levels while ascending. Never exceed the live finite range.
    if(!Number.isInteger(settings.max)||settings.max<0||settings.max>12)fail('UI_DRIFT','Unknown effort control.');
    for(let i=0;settings.effort!==target.effort && settings.index>0 && i<13;i++) {await control.press('ArrowLeft');settings=await this.settings();}
    for(let i=0;settings.effort!==target.effort && settings.index<settings.max && i<13;i++) {
      if(settings.index===settings.max-1 && !(this.surface==='chat'?target.effort==='Pro':['Ultra','울트라'].includes(target.effort))) fail('EFFORT_UNAVAILABLE','Do not enter the maximum tier merely to discover an unsupported level.');
      await control.press('ArrowRight');settings=await this.settings();}
    if(settings.model[0]!==target.model)fail('CONFIGURATION_MISMATCH','Model changed during effort selection.');
    if(settings.effort!==target.effort)fail('EFFORT_UNAVAILABLE',`Named effort ${target.effort} was not observed.`);
    await control.press('Escape');
    return {...target};
  }
  async prepare(text,paths) {
    await this.tab.playwright.locator(input).fill(text);
    if(paths.length) {
      await this.tab.playwright.getByTestId('composer-plus-btn').click();
      const upload=this.tab.playwright.getByText(/^(사진 및 파일 추가|Add photos & files)$/);
      if(await upload.count()!==1)fail('ATTACHMENT_FAILED','The visible upload action is unavailable.');
      // Attach a rejection handler immediately; a delayed click must not leave an unhandled chooser promise.
      const chooserPromise=this.tab.playwright.waitForEvent('filechooser',{timeoutMs:10000}).then(value=>({value}),error=>({error}));
      await upload.click();
      const event=await chooserPromise;
      if(event.error)fail('ATTACHMENT_FAILED',event.error.message);
      const chooser=event.value;
      if(paths.length>1&&!await chooser.isMultiple())fail('ATTACHMENT_FAILED','The current chooser only accepts one file.');
      await chooser.setFiles(paths);
    }
  }
  async attachmentState() {
    return this.tab.playwright.evaluate(form=>{
      const f=document.querySelector(form);
      return {removable:Array.from(f?.querySelectorAll('button[aria-label]')??[]).filter(e=>/(제거|Remove)/i.test(e.getAttribute('aria-label'))).length,names:Array.from(f?.querySelectorAll('[role="group"][aria-label]:has([data-default-action])')??[]).map(e=>e.getAttribute('aria-label')),
        pending:!!f?.querySelector('[role="progressbar"],.cursor-wait')||f?.querySelector('[data-testid="send-button"]')?.getAttribute('aria-disabled')==='true',errors:Array.from(document.querySelectorAll('[role="alert"]')).map(e=>e.textContent).filter(Boolean)};
    },form);
  }
  async attachmentsReady(paths) {
    const state=await this.attachmentState();
    if(state.errors.length)fail('ATTACHMENT_FAILED',state.errors.join('\n'));
    if(state.pending)return false;
    if(state.names.length>paths.length||state.removable!==state.names.length)fail('ATTACHMENT_FAILED','Unexpected or unrecognized attachments appeared in the composer.');
    if(state.names.length===paths.length && !paths.every(p=>state.names.includes(basename(p))))fail('ATTACHMENT_FAILED','Attachment filenames changed.');
    return paths.every(p=>state.names.includes(basename(p))) && state.names.length===paths.length;
  }
  async preflight(target,text,paths,destination,baseline) {
    if(await this.tab.url()!==this.expectedURL)fail('TURN_IDENTITY_AMBIGUOUS','Destination changed before Send.');
    const page=await this.read();
    if(!same(page.turns.map(t=>t.id),baseline))fail('TURN_IDENTITY_AMBIGUOUS','The conversation changed during preparation.');
    if((await this.composer()).text!==text)fail('UI_DRIFT','Prepared prompt changed.');
    await this.assertSurface(); await this.openPicker(); const settings=await this.settings();
    if(settings.model.length!==1||settings.model[0]!==target.model||settings.effort!==target.effort)fail('CONFIGURATION_MISMATCH','Final menu readback differs from execution settings.');
    await this.tab.playwright.locator(`${picker} [aria-keyshortcuts="ArrowLeft ArrowRight"]`).press('Escape');
    if(!await this.attachmentsReady(paths))fail('ATTACHMENT_FAILED','Required uploads are not ready.');
    return {...target};
  }
  async send() {
    const send=this.tab.playwright.getByRole('button',{name:/^(프롬프트 보내기|Send prompt|Send message)$/});
    if(await send.count()!==1||!await send.isEnabled())fail('DELIVERY_UNKNOWN','Send is unavailable after the submission boundary.');
    await send.click();
  }
  async read(known) {
    const url=await this.tab.url(),match=url.match(/^https:\/\/chatgpt\.com\/c\/([a-zA-Z0-9-]+)$/);
    if(known&&known.url!==url)fail('TURN_IDENTITY_AMBIGUOUS','The tab left the known conversation.');
    const turns=await this.tab.playwright.evaluate(messages=>{
      let user=null;
      // Read response content, excluding code-block toolbar labels such as Copy/Run.
      function answerText(node) {
        if(!node)return '';
        if(node.nodeType===3)return node.textContent??'';
        if(node.nodeType!==1||node.getAttribute('aria-hidden')==='true'||node.hasAttribute('hidden'))return '';
        if(node.tagName==='PRE'&&node.querySelector('code'))return '\n'+node.querySelector('code').textContent+'\n';
        if(node.tagName==='BUTTON')return node.hasAttribute('data-file-citation-primary-file-id')?(node.getAttribute('aria-label')??node.textContent):'';
        if(node.tagName==='BR')return '\n';
        const text=Array.from(node.childNodes).map(answerText).join('');
        return /^(P|DIV|LI|TR|H[1-6])$/.test(node.tagName)?'\n'+text+'\n':text;
      }
      const running=Array.from(document.querySelectorAll('main button')).some(e=>/^(답변 중지|Stop generating|Stop response)$/.test(e.getAttribute('aria-label')??''));
      return Array.from(document.querySelectorAll(`main ${messages}`)).map(e=>{
        const role=e.getAttribute('data-message-author-role'),id=e.getAttribute('data-message-id'),section=e.closest('[data-turn-id]');
        if(role==='user')user=id;
        const content=role==='assistant'?e.querySelector('.markdown'):e.querySelector('.whitespace-pre-wrap');
        return {id,role,parent_user_id:role==='assistant'?user:null,text:role==='assistant'?answerText(content).trim():(content?.innerText.trim()??''),
          code_blocks:Array.from(content?.querySelectorAll('pre code')??[]).map(e=>e.textContent??''),
          attachments:Array.from(section?.querySelectorAll('[role="group"][aria-label]:has([data-default-action])')??[]).map(e=>e.getAttribute('aria-label')),
          final:role==='assistant'&&!running&&!!section?.querySelector('[data-testid="copy-turn-action-button"]')&&!!content,
          artifacts:Array.from(section?.querySelectorAll('a[href],img[src],button[data-file-citation-primary-file-id]')??[]).map(e=>({kind:e.tagName==='IMG'?'image':e.tagName==='BUTTON'?'file':'link',id:e.getAttribute('data-file-citation-primary-file-id')??undefined,url:e.href??e.src??null,label:e.getAttribute('aria-label')??e.getAttribute('alt')??e.textContent??'',bytes_retrieved:false}))};
      });
    },messages);
    return {conversation:match?{url,id:match[1]}:null,turns};
  }
  async retrieve(answer) {
    const id=safeId(answer.id);
    const section=this.tab.playwright.locator(`[data-turn-id]`).filter({has:this.tab.playwright.locator(`[data-message-id="${id}"]`)});
    const before=await this.tab.clipboard.read();
    const sentinel=`gptplease-copy-${id}`;
    try {
      await this.tab.clipboard.writeText(sentinel);
      await section.getByTestId('copy-turn-action-button').click();
      let markdown=await this.tab.clipboard.readText();
      const artifacts=answer.artifacts.map(a=>({...a}));
      for(const match of markdown.matchAll(/\[([^\]]*)\]\((sandbox:[^)]+)\)/g)){
        const label=match[1]||match[2].split("/").pop();
        const file=artifacts.find(a=>a.kind==="file"&&a.label===label);
        if(file)file.url=match[2];else artifacts.push({kind:"file",label,url:match[2],bytes_retrieved:false});
        if(!match[1])markdown=markdown.replace(match[0],`[${label}](${match[2]})`);
      }
      const after=await this.read();
      const current=after.turns.find(t=>t.id===id);
      const complete=markdown!==sentinel&&!!markdown.trim()&&current?.final&&current.text===answer.text&&coversVisibleText(markdown,answer.text)&&
        (answer.code_blocks??[]).every(code=>markdown.replace(/\r\n/g,'\n').includes(code.replace(/\r\n/g,'\n').trimEnd()));
      return {assistant_turn_id:id,complete:!!complete,markdown:complete?markdown:null,artifacts};
    } finally {if(before.length)await this.tab.clipboard.write(before);else await this.tab.clipboard.writeText('');}
  }
  async cleanup(text,paths) {
    // Never clear another draft. Uploaded files require explicit UI removal and remain reported as incomplete cleanup.
    if((await this.composer()).text===text)await this.tab.playwright.locator(input).fill('');
    return paths.length===0;
  }
}
export class WorkAdapter extends ChatAdapter {
  constructor(tab) {super(tab);this.surface='work';}
  async assertSurface() {
    await super.assertSurface();
    const state=await this.composer();
    if(!state.buttons.some(b=>/^GPT-/.test(b.text)))fail('SURFACE_UNAVAILABLE','Work must expose its full model name in the composer.');
  }
}
