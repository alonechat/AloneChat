"""
Friend service for AloneChat server.

Provides friend management logic including friend requests, friendships, and notifications.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .database import get_database
from .user import get_user_service

logger = logging.getLogger(__name__)


@dataclass
class FriendRequest:
    id: str
    from_user: str
    to_user: str
    message: str
    status: str
    created_at: Any
    
    def to_dict(self) -> Dict[str, Any]:
        if self.created_at is None:
            created_at_val = None
        elif hasattr(self.created_at, 'isoformat'):
            created_at_val = self.created_at.isoformat()
        else:
            created_at_val = str(self.created_at)
        
        return {
            'id': self.id,
            'from_user': self.from_user,
            'to_user': self.to_user,
            'message': self.message,
            'status': self.status,
            'created_at': created_at_val
        }


@dataclass
class FriendInfo:
    user_id: str
    display_name: str
    remark: str
    status: str
    is_online: bool
    last_seen: Any
    
    def to_dict(self) -> Dict[str, Any]:
        if self.last_seen is None:
            last_seen_val = 0
        elif isinstance(self.last_seen, float):
            last_seen_val = self.last_seen
        elif isinstance(self.last_seen, int):
            last_seen_val = float(self.last_seen)
        elif hasattr(self.last_seen, 'timestamp'):
            last_seen_val = self.last_seen.timestamp()
        else:
            last_seen_val = 0
        
        return {
            'user_id': self.user_id,
            'display_name': self.display_name,
            'remark': self.remark,
            'status': self.status,
            'is_online': self.is_online,
            'last_seen': last_seen_val
        }


class FriendService:
    """Friend management service."""
    
    def __init__(self):
        self._db = get_database()
        self._user_service = get_user_service()
    
    def send_friend_request(self, from_user: str, to_user: str, message: str = "") -> Dict[str, Any]:
        """Send a friend request."""
        if from_user == to_user:
            return {'success': False, 'error': 'Cannot add yourself as friend'}
        
        if not self._user_service.user_exists(to_user):
            return {'success': False, 'error': 'User does not exist'}
        
        if self._db.is_friend(from_user, to_user):
            return {'success': False, 'error': 'Already friends'}
        
        if self._db.has_pending_request(from_user, to_user):
            return {'success': False, 'error': 'Pending request already exists'}
        
        request_id = str(uuid.uuid4())
        if self._db.create_friend_request(request_id, from_user, to_user, message):
            logger.info("Friend request sent: %s -> %s", from_user, to_user)
            return {
                'success': True,
                'request_id': request_id,
                'message': 'Friend request sent'
            }
        
        return {'success': False, 'error': 'Failed to send request'}
    
    def accept_friend_request(self, request_id: str, user_id: str) -> Dict[str, Any]:
        """Accept a friend request."""
        request = self._db.get_friend_request(request_id)
        
        if not request:
            return {'success': False, 'error': 'Request not found'}
        
        if request['to_user'] != user_id:
            return {'success': False, 'error': 'Not authorized'}
        
        if request['status'] != 'pending':
            return {'success': False, 'error': 'Request already processed'}
        
        if self._db.update_friend_request_status(request_id, 'accepted'):
            if self._db.add_friend(request['from_user'], request['to_user']):
                logger.info("Friend request accepted: %s <-> %s", request['from_user'], request['to_user'])
                return {'success': True, 'message': 'Friend request accepted'}
        
        return {'success': False, 'error': 'Failed to accept request'}
    
    def reject_friend_request(self, request_id: str, user_id: str) -> Dict[str, Any]:
        """Reject a friend request."""
        request = self._db.get_friend_request(request_id)
        
        if not request:
            return {'success': False, 'error': 'Request not found'}
        
        if request['to_user'] != user_id:
            return {'success': False, 'error': 'Not authorized'}
        
        if request['status'] != 'pending':
            return {'success': False, 'error': 'Request already processed'}
        
        if self._db.update_friend_request_status(request_id, 'rejected'):
            logger.info("Friend request rejected: %s -> %s", request['from_user'], request['to_user'])
            return {'success': True, 'message': 'Friend request rejected'}
        
        return {'success': False, 'error': 'Failed to reject request'}
    
    def remove_friend(self, user_id: str, friend_id: str) -> Dict[str, Any]:
        """Remove a friend."""
        if not self._db.is_friend(user_id, friend_id):
            return {'success': False, 'error': 'Not friends'}
        
        if self._db.remove_friend(user_id, friend_id):
            logger.info("Friend removed: %s <-> %s", user_id, friend_id)
            return {'success': True, 'message': 'Friend removed'}
        
        return {'success': False, 'error': 'Failed to remove friend'}
    
    def get_friends(self, user_id: str) -> List[FriendInfo]:
        """Get all friends of a user with their status."""
        friends_data = self._db.get_friends(user_id)
        result = []
        
        for friend in friends_data:
            friend_id = friend['friend_id']
            remark = friend['remark']
            
            user_info = self._user_service.get_user_info(friend_id)
            if user_info:
                result.append(FriendInfo(
                    user_id=friend_id,
                    display_name=user_info.display_name or friend_id,
                    remark=remark,
                    status=user_info.status.name.lower(),
                    is_online=user_info.status.name.lower() != 'offline',
                    last_seen=user_info.last_seen
                ))
            else:
                result.append(FriendInfo(
                    user_id=friend_id,
                    display_name=friend_id,
                    remark=remark,
                    status='offline',
                    is_online=False,
                    last_seen=None
                ))
        
        return result
    
    def get_pending_requests(self, user_id: str) -> List[FriendRequest]:
        """Get pending friend requests received by user."""
        requests = self._db.get_pending_friend_requests(user_id)
        return [FriendRequest(**r) for r in requests]
    
    def get_sent_requests(self, user_id: str) -> List[FriendRequest]:
        """Get pending friend requests sent by user."""
        requests = self._db.get_sent_friend_requests(user_id)
        return [FriendRequest(**r) for r in requests]
    
    def set_remark(self, user_id: str, friend_id: str, remark: str) -> Dict[str, Any]:
        """Set remark for a friend."""
        if not self._db.is_friend(user_id, friend_id):
            return {'success': False, 'error': 'Not friends'}
        
        if self._db.set_friend_remark(user_id, friend_id, remark):
            return {'success': True, 'message': 'Remark updated'}
        
        return {'success': False, 'error': 'Failed to update remark'}
    
    def is_friend(self, user_id: str, friend_id: str) -> bool:
        """Check if two users are friends."""
        return self._db.is_friend(user_id, friend_id)
    
    def search_users(self, query: str, current_user: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search for users by username."""
        all_users = self._user_service.get_all_users()
        query_lower = query.lower()
        
        results = []
        for user in all_users:
            user_id = user.get('user_id', '')
            if user_id == current_user:
                continue
            
            if query_lower in user_id.lower():
                is_friend = self._db.is_friend(current_user, user_id)
                has_pending = self._db.has_pending_request(current_user, user_id)
                
                results.append({
                    'user_id': user_id,
                    'display_name': user.get('display_name', user_id),
                    'status': user.get('status', 'offline'),
                    'is_online': user.get('is_online', False),
                    'is_friend': is_friend,
                    'has_pending_request': has_pending
                })
        
        return results[:limit]


_friend_service: Optional[FriendService] = None


def get_friend_service() -> FriendService:
    global _friend_service
    if _friend_service is None:
        _friend_service = FriendService()
    return _friend_service
