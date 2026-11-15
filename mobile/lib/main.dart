import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:qr_flutter/qr_flutter.dart';

const apiBaseUrl = String.fromEnvironment('API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000');
const secureStorage = FlutterSecureStorage();

void main() => runApp(const SocietyApp());

class Api {
  static Future<dynamic> call(String path, String token, {Map<String,dynamic>? body}) async {
    final headers = {'Content-Type':'application/json', 'Authorization':'Bearer $token'};
    final response = body == null
        ? await http.get(Uri.parse('$apiBaseUrl$path'), headers: headers)
        : await http.post(Uri.parse('$apiBaseUrl$path'), headers: headers, body: jsonEncode(body));
    final data = response.body.isEmpty ? {} : jsonDecode(response.body);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception(data['detail'] ?? 'Request failed (${response.statusCode})');
    }
    return data;
  }
}

class SocietyApp extends StatelessWidget {
  const SocietyApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Society Guest Registry', debugShowCheckedModeBanner: false,
    theme: ThemeData(colorSchemeSeed: const Color(0xFF176B56), useMaterial3: true),
    home: const SessionGate());
}

class SessionGate extends StatefulWidget {
  const SessionGate({super.key});
  @override
  State<SessionGate> createState() => _SessionGateState();
}
class _SessionGateState extends State<SessionGate> {
  String? token; Map<String,dynamic>? profile; bool loading = true;
  @override
  void initState() { super.initState(); restore(); }
  Future<void> restore() async {
    final saved = await secureStorage.read(key:'token');
    if (saved != null) {
      try { profile = await Api.call('/auth/me', saved); token = saved; }
      catch (_) { await secureStorage.delete(key:'token'); }
    }
    if (mounted) setState(() => loading = false);
  }
  void signedIn(String t, Map<String,dynamic> p) => setState(() { token=t; profile=p; });
  Future<void> signOut() async {
    await secureStorage.delete(key:'token');
    if (mounted) setState(() { token=null; profile=null; });
  }
  @override
  Widget build(BuildContext context) {
    if (loading) return const Scaffold(body: Center(child:CircularProgressIndicator()));
    if (token == null) return LoginPage(onLogin:signedIn);
    return HomePage(token:token!, profile:profile!, onSignOut:signOut);
  }
}

class LoginPage extends StatefulWidget {
  final void Function(String,Map<String,dynamic>) onLogin;
  const LoginPage({super.key,required this.onLogin});
  @override
  State<LoginPage> createState()=>_LoginPageState();
}
class _LoginPageState extends State<LoginPage> {
  final email=TextEditingController(), password=TextEditingController();
  bool busy=false; String? error;
  Future<void> login() async {
    setState(() {busy=true;error=null;});
    try {
      final r=await http.post(Uri.parse('$apiBaseUrl/auth/login'),
        headers:{'Content-Type':'application/json'},
        body:jsonEncode({'email':email.text.trim(),'password':password.text}));
      final data=jsonDecode(r.body);
      if(r.statusCode!=200) throw Exception(data['detail']??'Login failed');
      await secureStorage.write(key:'token',value:data['access_token']);
      widget.onLogin(data['access_token'], {'name':data['name'],'role':data['role'],'flat_number':data['flat_number']});
    } catch(e) {setState(()=>error=e.toString().replaceFirst('Exception: ',''));}
    finally {if(mounted)setState(()=>busy=false);}
  }
  @override
  void dispose(){email.dispose();password.dispose();super.dispose();}
  @override
  Widget build(BuildContext context)=>Scaffold(body:SafeArea(child:Center(child:SingleChildScrollView(
    padding:const EdgeInsets.all(24),child:ConstrainedBox(constraints:const BoxConstraints(maxWidth:440),
    child:Column(crossAxisAlignment:CrossAxisAlignment.stretch,children:[
      const Icon(Icons.apartment,size:64),const SizedBox(height:16),
      Text('Society Guest Registry',textAlign:TextAlign.center,style:Theme.of(context).textTheme.headlineSmall),
      const SizedBox(height:8),const Text('Sign in with your society account',textAlign:TextAlign.center),
      const SizedBox(height:28),
      TextField(controller:email,keyboardType:TextInputType.emailAddress,decoration:const InputDecoration(labelText:'Email',border:OutlineInputBorder())),
      const SizedBox(height:12),
      TextField(controller:password,obscureText:true,decoration:const InputDecoration(labelText:'Password',border:OutlineInputBorder()),onSubmitted:(_)=>login()),
      if(error!=null) Padding(padding:const EdgeInsets.only(top:12),child:Text(error!,style:TextStyle(color:Theme.of(context).colorScheme.error))),
      const SizedBox(height:18),FilledButton(onPressed:busy?null:login,child:Text(busy?'Signing in...':'Sign in')),
      const SizedBox(height:12),const Text('Accounts are created by your society administrator.',textAlign:TextAlign.center,style:TextStyle(color:Colors.grey))
    ]))))));
}

class HomePage extends StatefulWidget {
  final String token; final Map<String,dynamic> profile; final Future<void> Function() onSignOut;
  const HomePage({super.key,required this.token,required this.profile,required this.onSignOut});
  @override
  State<HomePage> createState()=>_HomePageState();
}
class _HomePageState extends State<HomePage> {
  Map<String,dynamic> stats={}; List visits=[]; bool busy=true; String? error;
  String get role=>widget.profile['role']??'guard';
  @override
  void initState(){super.initState();refresh();}
  Future<void> refresh() async {
    setState(()=>busy=true);
    try {
      final s=await Api.call('/dashboard/summary',widget.token);
      final v=await Api.call('/visitors',widget.token);
      stats=s;visits=v as List;
      error=null;
    } catch(e){error=e.toString();}
    if(mounted)setState(()=>busy=false);
  }
  Future<void> post(String path, [Map<String,dynamic>? body]) async {
    try {await Api.call(path,widget.token,body:body);
      if(mounted)ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content:Text('Saved')));
      await refresh();
    } catch(e){if(mounted)ScaffoldMessenger.of(context).showSnackBar(SnackBar(content:Text(e.toString())));}
  }
  Future<void> addVisitor() async {
    final form=GlobalKey<FormState>();
    final n=TextEditingController(),m=TextEditingController(),f=TextEditingController(),p=TextEditingController(),v=TextEditingController();
    final ok=await showDialog<bool>(context:context,builder:(c)=>AlertDialog(
      title:const Text('New visitor'),content:Form(key:form,child:SingleChildScrollView(child:Column(mainAxisSize:MainAxisSize.min,children:[
        field(n,'Visitor name'),field(m,'Mobile number'),field(f,'Flat number'),field(p,'Purpose'),field(v,'Vehicle number (optional)',required:false)
      ]))),
      actions:[TextButton(onPressed:()=>Navigator.pop(c,false),child:const Text('Cancel')),
        FilledButton(onPressed:()=>Navigator.pop(c,form.currentState!.validate()),child:const Text('Register'))]));
    if(ok==true) await post('/visitors',{'name':n.text.trim(),'mobile':m.text.trim(),'flat_number':f.text.trim(),'purpose':p.text.trim(),'vehicle_number':v.text.trim().isEmpty?null:v.text.trim()});
    n.dispose();m.dispose();f.dispose();p.dispose();v.dispose();
  }

  Future<void> issueQr(int visitorId) async {
    try {
      final result = await Api.call('/visitors/$visitorId/qr-pass', widget.token, body: {});
      if (!mounted) return;
      showDialog(context: context, builder: (c) => AlertDialog(
        title: const Text('Visitor QR pass'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          QrImageView(data: result['qr_token'], size: 210),
          const SizedBox(height: 8),
          const Text('Valid for 12 hours. Keep this pass private.')
        ]),
        actions: [TextButton(onPressed: () => Navigator.pop(c), child: const Text('Close'))],
      ));
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString())));
    }
  }

  Widget field(TextEditingController c,String label,{bool required=true})=>Padding(padding:const EdgeInsets.only(bottom:9),child:TextFormField(controller:c,decoration:InputDecoration(labelText:label,border:const OutlineInputBorder()),validator:(x)=>required&&(x==null||x.trim().isEmpty)?'Required':null));
  @override
  Widget build(BuildContext context){
    final resident=role=='resident', admin=role=='admin', guard=role=='guard';
    final title=admin?'Administrator':resident?'Resident':'Security desk';
    return Scaffold(appBar:AppBar(title:Text(title),actions:[
      IconButton(onPressed:refresh,icon:const Icon(Icons.refresh)),
      IconButton(onPressed:widget.onSignOut,icon:const Icon(Icons.logout))
    ]),
    floatingActionButton:(guard||admin)?FloatingActionButton.extended(onPressed:addVisitor,icon:const Icon(Icons.person_add),label:const Text('New visitor')):null,
    body:RefreshIndicator(onRefresh:refresh,child:ListView(padding:const EdgeInsets.all(16),children:[
      Text('Hello, ${widget.profile['name']??'User'}',style:Theme.of(context).textTheme.headlineSmall),
      if(resident)Text('Flat ${widget.profile['flat_number']??''}'),
      const SizedBox(height:16),if(busy)const LinearProgressIndicator(),
      if(error!=null)Text(error!,style:TextStyle(color:Theme.of(context).colorScheme.error)),
      Wrap(spacing:8,runSpacing:8,children:['Total','Pending','Inside','Exited'].map((k){
        final key=k.toLowerCase();return SizedBox(width:145,child:Card(child:Padding(padding:const EdgeInsets.all(12),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
          Text('${stats[key]??0}',style:Theme.of(context).textTheme.headlineMedium),Text(k)
        ]))));
      }).toList()),
      const SizedBox(height:18),Text(resident?'Approval requests':'Visitor register',style:Theme.of(context).textTheme.titleLarge),
      if(visits.isEmpty&&!busy)const Card(child:Padding(padding:EdgeInsets.all(18),child:Text('No visitor records yet.'))),
      ...visits.map((item){
        final x=item as Map<String,dynamic>;final id=x['id'];final status=x['status'];
        return Card(child:Padding(padding:const EdgeInsets.all(12),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
          Text(x['name']??'Visitor',style:const TextStyle(fontWeight:FontWeight.bold,fontSize:16)),
          Text('Flat ${x['flat_number']} · ${x['purpose']}'),
          Text('Mobile: ${x['mobile']}'),
          Row(children:[Chip(label:Text(status.toString().toUpperCase())),const Spacer(),
            if(resident&&status=='pending')TextButton(onPressed:()=>post('/visitors/$id/decision',{'approved':false}),child:const Text('Reject')),
            if(resident&&status=='pending')FilledButton(onPressed:()=>post('/visitors/$id/decision',{'approved':true}),child:const Text('Approve')),
            if((guard||admin)&&status=='approved')TextButton(onPressed:()=>issueQr(id),child:const Text('QR pass')),
            if((guard||admin)&&status=='approved')FilledButton(onPressed:()=>post('/visitors/$id/check-in'),child:const Text('Check in')),
            if((guard||admin)&&status=='inside')FilledButton(onPressed:()=>post('/visitors/$id/check-out'),child:const Text('Check out'))
          ])
        ])));
      }),
      if(admin)const Card(child:ListTile(leading:Icon(Icons.manage_accounts),title:Text('User management'),subtitle:Text('Create accounts through the protected /admin/users endpoint. Full in-app management form is next.'))),
      if(admin)const Card(child:ListTile(leading:Icon(Icons.domain),title:Text('Society structure'),subtitle:Text('Manage buildings and flats through /admin/buildings and /admin/flats.'))),
      if(admin)const Card(child:ListTile(leading:Icon(Icons.download),title:Text('Visitor reports'),subtitle:Text('Export CSV from /reports/visitors.csv.'))),
      if(guard)const Padding(padding:EdgeInsets.only(top:8),child:Text('A resident must approve a visitor before check-in.'))
    ])));
  }
}
