import asyncio
import json
import datetime

from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from electrum.i18n import _
from electrum.gui.qt.util import MyTreeView, MessageBoxMixin, WindowModalDialog, Buttons, CancelButton,OkButton
from electrum import util 
#from electrum.util import print_error

import sys
import time
import os
# sys.path.insert(0,os.path.join(os.path.dirname(__file__), 'monstr'))
sys.path.insert(0,os.path.dirname(__file__))
from monstr.encrypt import Keys
from monstr.client.client import ClientPool
from monstr.event.event import Event
from monstr.util import util_funcs


class store_stub:
    # btc electrum doesn't seem to have the store used by the cash version or at least it's not in the
    # sample place - for now stubb a version of the store that just uses a CVV file
    def __init__(self):
        self._store_file = os.path.join(os.path.dirname(__file__), 'nonstr.json')
        self._store = {}
        self.read()

    def get(self, name):
        ret = None
        if name in self._store:
            ret = self._store[name]
        return ret

    def put(self, name, value):
        self._store[name] = value

    def read(self):
        try:
            with open(self._store_file, 'r') as f:
                self._store = json.loads(f.read())
        except FileNotFoundError as fe:
            # not created yet?
            pass

    def write(self):
        with open(self._store_file, 'w') as f:
            f.write(json.dumps(self._store))


class Ui(MyTreeView, MessageBoxMixin):

    receive_refresh_feed_trigger = pyqtSignal(str)

    def __init__(self, parent, plugin, wallet_name):
        self._plugin = plugin
        self._wallet_name = wallet_name

        self.create_main_gui(parent)

        # Set up trigger so we can call back into the ui from the p2pnetwork threads. 
        self.receive_refresh_feed_trigger.connect(self.process_refresh_feed_message)

        # replace make a store
        # cash version replace with self.parent.wallet
        self._local_store = store_stub()
        # Update the UI.
        self.update_friends_list()
        self.update_relays_list()
        self.update_alias_list()

        # loop to run async code in
        self._loop = asyncio.new_event_loop()

        # alias that is currently in use, posts will be from this alias
        # and the feed view will be showing events for this profile and those it follows
        self._current_alias = None
        # if we have an alias set then this will init it
        self.current_alias = None

    def create_main_gui(self, parent):
        # An initial widget is required.
        MyTreeView.__init__(self, parent, self.create_menu)
        vbox = QVBoxLayout()
        vbox2 = QVBoxLayout()
        vbox3 = QVBoxLayout()
        vbox4 = QVBoxLayout()
        vbox5 = QVBoxLayout()
        vbox6 = QVBoxLayout()
        vbox7 = QVBoxLayout()
        self.setLayout(vbox)
        label20 = QLabel(_("Your Feed"))
        label20.setAlignment(Qt.AlignCenter)
        f = label20.font()
        f.setPointSize(18)
        label20.setFont(f)
        hbox20 = QHBoxLayout()
        hbox20.addWidget(label20)
        vbox5.addLayout(hbox20)
        self.event_view_area = QTextEdit()
        hbox7 = QHBoxLayout()
        hbox7.addWidget(self.event_view_area)
        vbox5.addLayout(hbox7)
        self.refresh_feed_button = QPushButton(_("REFRESH FEED"))
        hbox9 = QHBoxLayout()
        hbox9.addWidget(self.refresh_feed_button)
        vbox5.addLayout(hbox9)
        my_line = QFrame()
        my_line.setLineWidth(3)
        my_line.setMidLineWidth(3)
        my_line.setFrameShape(QFrame.HLine)
        my_line.setFrameShadow(QFrame.Sunken)
        vbox5.addWidget(my_line)
        self.refresh_feed_button.clicked.connect(self.refresh_feed_view)

        # Chat message widgets
        self.chatarea = QTextEdit()
        self.my_chat_msg = QLineEdit()
        self.message_button = QPushButton(_("Send Message"))
        hbox3 = QHBoxLayout()
        self.message_button.clicked.connect(self.send_nostr_msg)
        hbox4 = QHBoxLayout()
        my_line2 = QFrame()
        my_line2.setLineWidth(3)
        my_line2.setMidLineWidth(3)
        my_line2.setFrameShape(QFrame.HLine)
        my_line2.setFrameShadow(QFrame.Sunken)
        vbox6.addWidget(my_line2)
        label21 = QLabel(_("Post Your Messages"))
        label21.setAlignment(Qt.AlignCenter)
        f = label21.font()
        f.setPointSize(18)
        label21.setFont(f)
        vbox6.addWidget(label21)
        hbox22 = QHBoxLayout()
        hbox22.addWidget(self.my_chat_msg)
        hbox22.addWidget(self.message_button)
        vbox6.addLayout(hbox22)

        ######################################################

        hbox23 = QHBoxLayout()
        label23 = QLabel(_("Manage Friends, IDs, and Relays"))
        label23.setAlignment(Qt.AlignCenter)
        f = label23.font()
        f.setPointSize(18)
        label23.setFont(f)
        hbox23.addWidget(label23)
        hbox1 = QHBoxLayout()
        label = QLabel(_("FRIENDS LIST"))
        hbox1.addWidget(label)
        vbox4.addLayout(hbox1)
        self.friends_list = QTreeWidget()
        self.friends_list.setColumnCount(2)
        self.friends_list.setHeaderLabels([_('Name'), _('Pubkey')])
        self.friends_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.friends_list.customContextMenuRequested.connect(self.create_friends_list_menu)
        hbox13 = QHBoxLayout()
        hbox13.addWidget(self.friends_list)
        vbox4.addLayout(hbox13)
        self.new_friend_button = QPushButton(_("Add New Friend"))
        self.new_friend_button.clicked.connect(self.new_friend_dialog)
        hbox11 = QHBoxLayout()
        hbox11.addWidget(self.new_friend_button)
        vbox4.addLayout(hbox11)

        ##########################################################################

        hbox12 = QHBoxLayout()
        label12 = QLabel(_("RELAYS LIST"))
        hbox12.addWidget(label12)
        vbox2.addLayout(hbox12)

        self.relays_list = QTreeWidget()
        self.relays_list.setColumnCount(1)
        self.relays_list.setHeaderLabels([_('Relay')])
        self.relays_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.relays_list.customContextMenuRequested.connect(self.create_relays_list_menu)
        hbox10 = QHBoxLayout()
        hbox10.addWidget(self.relays_list)
        vbox2.addLayout(hbox10)
        self.new_relay_button = QPushButton(_("Add New Relay"))
        self.new_relay_button.clicked.connect(self.new_relay_dialog)
        hbox14 = QHBoxLayout()
        hbox14.addWidget(self.new_relay_button)
        vbox2.addLayout(hbox14)
        hbox15 = QHBoxLayout()
        label15 = QLabel(_("ALIAS LIST"))
        hbox15.addWidget(label15)
        vbox3.setAlignment(Qt.AlignTop)
        vbox3.addLayout(hbox15)
        self.alias_combo = QComboBox()
        self.alias_combo.currentIndexChanged.connect(self.on_alias_change)
        hbox16 = QHBoxLayout()
        hbox16.addWidget(self.alias_combo)
        vbox3.addLayout(hbox16)
        self.new_alias_button = QPushButton(_("Add New Alias"))
        self.new_alias_button.clicked.connect(self.new_alias_dialog)
        hbox17 = QHBoxLayout()
        hbox17.addWidget(self.new_alias_button)
        vbox3.addLayout(hbox17)
        self.copy_pubkey_button = QPushButton(_("Copy Alias Pubkey to Clipboard"))
        self.copy_pubkey_button.clicked.connect(self.copy_pubkey)
        hbox18 = QHBoxLayout()
        hbox18.addWidget(self.copy_pubkey_button)
        vbox3.addLayout(hbox18)

        # Stack a few widgets into a row here.
        hbox19 = QHBoxLayout()
        hbox19.addLayout(vbox4)
        hbox19.addLayout(vbox2)
        hbox19.addLayout(vbox3)

        # Add remaining widgets
        vbox.addLayout(vbox5)
        vbox7.addLayout(hbox23)
        vbox7.addLayout(hbox19)
        vbox.addLayout(vbox7)
        vbox.addLayout(hbox1)
        vbox.addLayout(hbox3)
        vbox.addLayout(hbox4)
        vbox.addLayout(vbox6)


    def create_friends_list_menu(self, position):
        # This function creates the right click menu for the friends list.
        menu = QMenu()
        delete_option = menu.addAction("Delete Friend")
        copy_pubkey_option = menu.addAction("Copy Pubkey")
        copy_bech32_option = menu.addAction("Copy Pubkey as bech32")
        my_row = self.friends_list.selectedItems()[0] 
        name = my_row.text(0)
        pubkey = my_row.text(1) 
        delete_option.triggered.connect(lambda: self.delete_friend(name,pubkey)) 
        copy_pubkey_option.triggered.connect(lambda: self.doCopy(pubkey))
        copy_bech32_option.triggered.connect(lambda: self.doBech32Copy(pubkey))
        menu.exec_(self.viewport().mapToGlobal(position))


    def new_friend_dialog(self):
        # This function creates the dialog window for creating a new friend.
        d = WindowModalDialog(self.top_level_window(), _("New Friend"))
        vbox = QVBoxLayout(d)
        vbox.addWidget(QLabel(_('New Friend') + ':'))
        grid = QGridLayout()
        line1 = QLineEdit()
        line1.setFixedWidth(350)
        line2 = QLineEdit()
        line2.setFixedWidth(350)
        grid.addWidget(QLabel(_("Name")), 1, 0)
        grid.addWidget(line1, 1, 1)
        grid.addWidget(QLabel(_("Pubkey")), 2, 0)
        grid.addWidget(line2, 2, 1)
        vbox.addLayout(grid)
        vbox.addLayout(Buttons(CancelButton(d), OkButton(d)))
        if d.exec_():
            name = line1.text().strip()
            pubkey = line2.text().strip() 
            self.create_friend(name, pubkey)

    def delete_friend(self,name, pubkey):
        # This function deletes a friend.
        nostron_friend= dict(name = str(name), pubkey = str(pubkey))
        existing_list= self._local_store.get('nostron_friends')
        existing_list.remove(nostron_friend)
        self._local_store.put('nostron_friends', existing_list)
        self._local_store.write()
        self.update_friends_list()

    def create_friend(self, name, pubkey):
        # This function creates a new friend.
        if len(str(name)) > 20:
            self.show_error(_('Names should be 20 chars or less.'))
        
        if len(str(name)) < 1:
            self.show_error(_('Name cannot be empty.'))

        if not Keys.is_hex_key(str(pubkey)):
            if not Keys.is_bech32_key(str(pubkey)):
                self.show_error(_('Pubkey must be in proper hex or bech32 format.'))
                return
            else:
                # User entered bech32 format.  Fine, but let's convert to hex to standardize storage.
                pubkey = Keys.bech32_to_hex(str(pubkey))
            
        nostron_friend = dict(name = str(name), pubkey = str(pubkey))
         
        existing_list = self._local_store.get('nostron_friends')
        if existing_list is None:
            existing_list = []
        existing_list.append(nostron_friend)
        self._local_store.put('nostron_friends', existing_list)
        self._local_store.write()
        self.update_friends_list()
    
    def update_friends_list(self):
        # This function updates the friends list.
        self.friends_list.clear()
        my_friend_list = self._local_store.get('nostron_friends')
        l = []
        if my_friend_list is None: 
            return
        for i in my_friend_list:
            friend_name = i.get('name')
            friend_pubkey = i.get('pubkey')
            my_row_text = []
            my_row_text.append(friend_name)
            my_row_text.append(friend_pubkey)
            l.append(QTreeWidgetItem(my_row_text))
        self.friends_list.addTopLevelItems(l)
            
    def doBech32Copy(self,txt):
        # This is a helper function to get the pubkey in bech32 format.
        txt = Keys.hex_to_bech32(str(txt))
        self.doCopy(txt)

    def doCopy(self,txt):
        # This is a helper function for cliboard copy. copy_to_clipboard should be available from main_window so just call parent.
        txt = txt.strip() 
        self.parent.copy_to_clipboard(txt)

    def create_relays_list_menu(self, position):
        # This function creates the right click menu for relays list.
        menu = QMenu()
        delete_option = menu.addAction("Delete Relay") 
        my_row = self.relays_list.selectedItems()[0] 
        name = my_row.text(0)
        delete_option.triggered.connect(lambda: self.delete_relay(name))  
        menu.exec_(self.viewport().mapToGlobal(position))
        
    def new_relay_dialog(self):
        # This function creates a dialog window for creating a new relay.
        d = WindowModalDialog(self.top_level_window(), _("New Relay"))
        vbox = QVBoxLayout(d)
        vbox.addWidget(QLabel(_('New Relay') + ':'))
        grid = QGridLayout()
        line1 = QLineEdit()
        line1.setFixedWidth(350)
        line2 = QLineEdit()
        line2.setFixedWidth(350)
        grid.addWidget(QLabel(_("Relay")), 1, 0)
        grid.addWidget(line1, 1, 1)
        vbox.addLayout(grid)
        vbox.addLayout(Buttons(CancelButton(d), OkButton(d)))
        if d.exec_():
            relay = line1.text().strip()
            self.create_relay(relay)
            
    def delete_relay(self,relay):
        # This function deletes a relay.
        nostron_relay= dict(relay = str(relay))
        existing_list = self._local_store.get('nostron_relays')
        existing_list.remove(nostron_relay)
        self._local_store.put('nostron_relays', existing_list)
        self._local_store.write()
        self.update_relays_list()

    def create_relay(self, relay):
        # This function creates a new relay.
        if len(str(relay)) > 200:
            self.show_error(_('Relays should be 200 chars or less.'))
        
        if len(str(relay)) < 1:
            self.show_error(_('Relay cannot be empty.'))
               
        nostron_relay= dict(relay = str(relay))
         
        existing_list= self._local_store.get('nostron_relays')
        if existing_list is None:
            existing_list = []
        existing_list.append(nostron_relay)
        self._local_store.put('nostron_relays', existing_list)
        self._local_store.write()
        self.update_relays_list()
    
    def update_relays_list(self):
        # This function updates the list of relays.
        self.relays_list.clear()
        my_relays_list = self._local_store.get('nostron_relays')
        l = []
        if my_relays_list is None: 
            return
        for i in my_relays_list:
            relays_name = i.get('relay') 
            my_row_text = []
            my_row_text.append(relays_name) 
            l.append(QTreeWidgetItem(my_row_text))
        self.relays_list.addTopLevelItems(l)
                     
    def new_alias_dialog(self):
        # This function creates the dialog window for createing new alias.
        d = WindowModalDialog(self.top_level_window(), _("New Alias"))
        vbox = QVBoxLayout(d)
        vbox.addWidget(QLabel(_('Leave Privkey blank unless importing an existing key.')))
        grid = QGridLayout()
        line1 = QLineEdit()
        line1.setFixedWidth(350)
        line2 = QLineEdit()
        line2.setFixedWidth(350)
        grid.addWidget(QLabel(_("Alias")), 1, 0)
        grid.addWidget(line1, 1, 1)
        
        grid.addWidget(QLabel(_("Privkey")), 2, 0)
        grid.addWidget(line2, 2, 1)
        
        vbox.addLayout(grid)
        vbox.addLayout(Buttons(CancelButton(d), OkButton(d)))
        if d.exec_():
            alias = line1.text().strip()
            privkey = line2.text().strip()
            self.create_alias(alias,privkey)

    def create_alias(self, alias,privkey): 
        # This function creates a new alias for the user.
        if len(str(alias)) > 30:
            self.show_error(_('Alias should be 30 chars or less.'))
            return
        if len(str(alias)) < 1:
            self.show_error(_('Alias cannot be empty.'))
            return
        
        existing_list = self._local_store.get('nostron_aliases')
        if existing_list is not None:
            for i in existing_list:
                alias_name= i.get('alias') 
                if alias == alias_name:
                    self.show_error(_('You already have an alias with that name.'))
                    return
         
        # If private key is blank, create new keypair.
        if privkey == "":
            new_key_pair = Keys.get_new_key_pair()
            privkey = new_key_pair.get('priv_k')
            pubkey = new_key_pair.get('pub_k') 
        else:
            # Private key is not blank, user is importing a key.
            try:
                if privkey[0:4] == "nsec":
                    #Convert from bech32
                    privkey = Keys.bech32_to_hex(privkey)
                new_key_pair = Keys.get_new_key_pair(priv_key=privkey)
                privkey = new_key_pair.get('priv_k')
                pubkey = new_key_pair.get('pub_k')
            except:
                self.show_error(_('Invalid private key.'))
                return
        
        nostron_alias= dict(alias = str(alias), pubkey = str(pubkey), privkey = str(privkey))
        if existing_list is None:
            existing_list = []
            nostron_chosen_alias = dict(chosen_alias = str(alias))
            self._local_store.put('nostron_chosen_alias', nostron_chosen_alias)
        existing_list.append(nostron_alias)
        self._local_store.put('nostron_aliases', existing_list)
        self._local_store.write()
        self.update_alias_list()
    
    def update_alias_list(self):
        # This function updates the alias list widget
        my_alias_list = self._local_store.get('nostron_aliases')
        alias_choices = []
        if my_alias_list is None: 
            return
        
        # Grab the selected choice from storage.
        chosen_alias_dict = self._local_store.get('nostron_chosen_alias')
        chosen_alias_name = chosen_alias_dict.get('chosen_alias')
        
        # keep track of the qcombobox index so we can grab the right default value.
        my_index = 0
        chosen_index = 0
        
        for i in my_alias_list:
            alias_name = i.get('alias') 
            
            alias_choices.append(alias_name) 
            if alias_name == chosen_alias_name:
                chosen_index=my_index
            my_index +=1     
            
        self.alias_combo.clear()
        self.alias_combo.addItems(alias_choices)
        # Reflect chosen alias in the dropdown.
        self.alias_combo.setCurrentIndex(chosen_index)

    def on_alias_change(self):
        # This is a function to update storage when the alias dropdown is selected.
        current_alias = self.alias_combo.currentText()
        nostron_chosen_alias=dict(chosen_alias = str(current_alias))
        self._local_store.put('nostron_chosen_alias', nostron_chosen_alias)
        self._local_store.write()
               
    def copy_pubkey(self):
        # This is a helper function to copy a key to the clipboard.
        pubkey=""           
        my_alias_list = self._local_store.get('nostron_aliases')
        chosen_alias = self._local_store.get('nostron_chosen_alias')
        chosen_alias_name = chosen_alias.get('chosen_alias')
        for i in my_alias_list:
            alias_name = i.get('alias') 
            if alias_name == chosen_alias_name:
                pubkey=i.get('pubkey')
        # Copy to clipboard  
        self.doBech32Copy(pubkey)
               
    # Functions for the plugin architecture.
    def create_menu(self):
        pass

    def on_delete(self):
        pass

    def on_update(self):
        pass
        
    def send_nostr_msg(self):
        # This function sends a message to the network.
        post_message = self.my_chat_msg.text()
        
        # Do not post empty messages, just exit.
        if post_message == "":
            return

        relays = self._local_store.get('nostron_relays')
        if not relays:
            self.show_error("No relays set, add a relay before posting")
            return

        if not self.current_alias:
            self.show_error("No alias is current set for posting")
            return

        confirm_msg = "Post this message to the network?"
        if self.question(confirm_msg):
            try:
                asyncio.run_coroutine_threadsafe(self.do_post(the_message=post_message,
                                                              relays=relays,
                                                              priv_k=self.current_alias['privkey']),
                                                 asyncio.get_event_loop())

            except Exception as e:
                print(e)

    @property
    def relays(self):
        return self._local_store.get('nostron_relays')

    @property
    def my_friends(self):
        # this should change to only being friends of the current alias and come from nostr
        # maybe on adding friends we should enable just local or public whre the contact is posted to nostr
        return self._local_store.get('nostron_friends')

    @property
    def my_aliases(self):
        return self._local_store.get('nostron_aliases')

    @property
    def current_alias_name(self):
        # used for posting at the moment but probably should reflect the view and friends we see
        ret = None
        c_alias = self._local_store.get('nostron_chosen_alias')
        if c_alias:
            ret = c_alias['chosen_alias']
        return ret

    @current_alias_name.setter
    def current_alias_name(self, the_alias):
        self._local_store.put('nostron_chosen_alias', the_alias)

    @property
    def current_alias(self):
        return self._current_alias

    @current_alias.setter
    def current_alias(self, name=None):
        # probably this is the initial init, get from store
        if not name:
            name = self.current_alias_name

        self._current_alias = None
        if name:
            for c_alias in self.my_aliases:
                # found selected alias
                if c_alias['alias'] == name:
                    self._current_alias = c_alias
                    break

            if self._current_alias and name != self._current_alias['alias']:
                self._local_store.put('nostron_chosen_alias', name)

        return self._current_alias

    async def do_post(self,
                      the_message: str,
                      relays: [str],
                      priv_k: str):

        k = Keys(priv_k=priv_k)
        n_evt = Event(kind=1,
                      content=the_message,
                      pub_key=k.public_key_hex())
        n_evt.sign(k.private_key_hex())
        self.my_chat_msg.setText("")
        # change this to use a clientpool that is made at class level
        try:
            urls = [r['relay'] for r in relays]
            async with ClientPool(urls) as c:
                c.publish(n_evt)
                # do something better here, if relay supports NIP20 cmds then we could wait for OK messages
                # else we could do tmp sub and see if the event comes in?
                await asyncio.sleep(1)

            # obvs this is junk, itll only update when we post, manual refresh required to see message to us
            # until we have it running in background though...
            await self.fetch_feed()
        except Exception as e:
            print(e)
        # self.show_error("One or more relays failed to post.")

    def refresh_feed_view(self):
        try:
            asyncio.run_coroutine_threadsafe(self.fetch_feed(),
                                             asyncio.get_event_loop())
        except Exception as e:
            print(e)

    async def fetch_feed(self):
        events = await self.get_messages()
        self.update_feed_list(events)

    def update_feed_list(self, events):
        txt_arr = []
        c_evt: Event
        name_map = {
            self.current_alias['pubkey']: 'me'.rjust(15)
        }
        for c_friend in self.my_friends:
            name_map[c_friend['pubkey']] = c_friend['name'][:15].rjust(15)

        def get_name(pubkey):
            ret  = '?'
            if pubkey in name_map:
                ret = name_map[pubkey]
            return ret

        for c_evt in events:
            txt_arr.append('%s@' % get_name(c_evt.pub_key))
            txt_arr.append('%s: ' % util_funcs.ticks_as_date(c_evt.created_at_ticks))

            txt_arr.append(c_evt.content)
            txt_arr.append("\r\n")
        self.receive_refresh_feed_message(''.join(txt_arr))

        # event_dict = []
        # for c_evt in events:
        #
        #     # Start with the pubkey. who is this?
        #     display_name = ""
        #     pubkey = str(c_evt._pub_key)
        #     l = []
        #     for i in my_friend_list:
        #         friend_name = i.get('name')
        #         alias_name = i.get('alias')
        #         friend_pubkey = i.get('pubkey')
        #         if alias_name is not None:
        #             friend_name = alias_name + "(me)"
        #         if pubkey == friend_pubkey:
        #             display_name = friend_name
        #
        #     event_dict.append(
        #         {"created_at": c_evt._created_at, "display_name": str(display_name), "content": c_evt._content})
        #
        # def get_created_at(msg):
        #     return msg.get('created_at')
        #
        # # Sort by date stamp
        # event_dict.sort(key=get_created_at)
        # for i in event_dict:
        #     epoch_time = i.get('created_at')
        #     date_time = datetime.datetime.fromtimestamp(epoch_time)
        #     event_text = str(date_time) + " | " + i.get('display_name') + ": " + i.get('content') + "\r\n"
        #     all_events = all_events + event_text
        # self.receive_refresh_feed_message(all_events)

    async def get_messages(self):
        urls = [r['relay'] for r in self.relays]
        friends_keys = [f['pubkey'] for f in self.my_friends]
        async with ClientPool(urls) as c:
            ret = await c.query({
                'kinds': [Event.KIND_TEXT_NOTE],
                'authors': friends_keys + [self.current_alias['pubkey']]
            })

        Event.sort(ret,
                   reverse=False,
                   inplace=True)

        return ret

    # DEAL WITH INCOMING MESSAGES 
       
    def receive_refresh_feed_message(self,incoming_message):
        self.receive_refresh_feed_trigger.emit(str(incoming_message))
    
      
    def process_refresh_feed_message(self,incoming_message): 
     
        self.feed_history = incoming_message
        self.event_view_area.setText(self.feed_history) 
        
       
         

  
        
        
        
        
        
                            
