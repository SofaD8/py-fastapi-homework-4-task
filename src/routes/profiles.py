from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import get_db, UserModel, UserProfileModel, UserGroupEnum
from schemas.profiles import ProfileCreateSchema, ProfileResponseSchema
from storages import S3StorageInterface
from config.dependencies import get_s3_storage_client, get_jwt_auth_manager
from security.interfaces import JWTAuthManagerInterface
from security.http import get_token
from exceptions.security import TokenExpiredError, InvalidTokenError

router = APIRouter()


@router.post("/users/{user_id}/profile/", response_model=ProfileResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_profile(
    user_id: int,
    request: Request,
    profile_data: ProfileCreateSchema = Depends(ProfileCreateSchema.as_form),
    avatar: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    s3_client: S3StorageInterface = Depends(get_s3_storage_client),
    auth_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager)
):
    # 1. Token Validation
    token = get_token(request)
    try:
        payload = auth_manager.decode_access_token(token)
    except TokenExpiredError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired.")
    except InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    current_user_id = payload.get("sub")
    if current_user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")
    
    current_user_id = int(current_user_id)

    # Fetch both current user (for permissions) and target user
    from sqlalchemy.orm import selectinload
    query = select(UserModel).options(selectinload(UserModel.group)).where(UserModel.id.in_([current_user_id, user_id]))
    result = await db.execute(query)
    users = {u.id: u for u in result.scalars().all()}

    current_user = users.get(current_user_id)

    if not current_user or not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or not active.")

    target_user = users.get(user_id)

    if not target_user or not target_user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or not active.")

    is_admin = current_user and current_user.group and current_user.group.name == UserGroupEnum.ADMIN.value
    if current_user_id != user_id and not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to edit this profile.")

    # 4. Check for Existing Profile
    query_profile = select(UserProfileModel).where(UserProfileModel.user_id == user_id)
    result_profile = await db.execute(query_profile)
    if result_profile.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already has a profile.")

    # 5. Avatar Upload to S3 Storage
    avatar.file.seek(0)

    try:
        from validation import validate_image

        validate_image(avatar)

        file_data = await avatar.read()

        file_extension = avatar.filename.rsplit('.', 1)[-1].lower()
        s3_path = f"avatars/{user_id}_avatar.{file_extension}"

        avatar_url = await s3_client.upload_file(s3_path, file_data)

        if not avatar_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to upload avatar. Please try again later."
            )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        import logging

        logging.error(f"S3 upload error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload avatar. Please try again later."
        )

    # 6. Profile Creation and Storage
    new_profile = UserProfileModel(
        user_id=user_id,
        first_name=profile_data.first_name,
        last_name=profile_data.last_name,
        gender=profile_data.gender,
        date_of_birth=profile_data.date_of_birth,
        info=profile_data.info,
        avatar=avatar_url
    )
    db.add(new_profile)
    await db.commit()
    await db.refresh(new_profile)

    return new_profile
