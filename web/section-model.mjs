export const sectionLabels = {education:'教育经历', employment:'工作与实习', project:'项目经历', academic:'学术成果', competition:'竞赛成果', skills:'专业技能', awards:'获奖经历', custom:'自定义'};

export function hasTimeline(type) {
  return ['education', 'employment', 'project', 'academic', 'competition', 'custom'].includes(type);
}

export function entryFields(type) {
  return {
    education:[['school','学校'],['degree','学历/学位'],['field_of_study','专业'],['location','地点']],
    employment:[['organization','单位'],['role','职位'],['location','地点']],
    project:[['name','项目名称'],['role','职责'],['url','项目网址']],
    academic:[['heading','条目标题'],['role','个人角色'],['url','成果链接（选填）']],
    competition:[['heading','条目标题'],['role','个人角色'],['url','成果链接（选填）']],
    custom:[['heading','条目标题'],['role','个人角色'],['url','相关链接（选填）']],
    skills:[], awards:[],
  }[type];
}

export function createEntry(type, id) {
  if (!Object.hasOwn(sectionLabels, type)) throw new Error('Unknown section type');
  const entry = {id, visible:true, body:''};
  const values = {
    education:{school:'',degree:'',field_of_study:'',location:''},
    employment:{organization:'',role:'',location:'',employment_type:'full_time'},
    project:{name:'',role:'',url:null},
    academic:{heading:'',role:'',url:null}, competition:{heading:'',role:'',url:null},
    custom:{heading:'',role:'',url:null}, skills:{label:''}, awards:{heading:''},
  };
  Object.assign(entry, values[type]);
  if (hasTimeline(type)) Object.assign(entry, {start_date:null, end_date:null, ongoing:false});
  return entry;
}
